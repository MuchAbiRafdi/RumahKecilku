from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.media_service import normalize_video


class ActivityRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._normalized_media_cache: dict[str, tuple[bytes, str]] = {}

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daycare_activities (
                    id TEXT PRIMARY KEY,
                    child_id TEXT NOT NULL,
                    child_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    note TEXT NOT NULL,
                    session TEXT NOT NULL,
                    time TEXT NOT NULL,
                    share_to_parent INTEGER NOT NULL,
                    announcement_json TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(daycare_activities)")}
            additive_columns = {
                "created_by": "TEXT",
                "duration_minutes": "INTEGER",
                "mood": "TEXT",
                "participation": "TEXT",
                "water_ml": "INTEGER",
                "meal_id": "TEXT",
                "meal_servings": "REAL NOT NULL DEFAULT 1",
                "meal_snapshot_json": "TEXT",
                "photo_blob": "BLOB",
                "photo_content_type": "TEXT",
                "media_blob": "BLOB",
                "media_content_type": "TEXT",
            }
            for column, column_type in additive_columns.items():
                if column not in columns:
                    connection.execute(f"ALTER TABLE daycare_activities ADD COLUMN {column} {column_type}")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_daycare_activity_child_created ON daycare_activities(child_id, created_at DESC)"
            )

    def seed_demo_samples(self) -> int:
        """Seed synthetic activity history for preview analytics only."""
        now = datetime.now(timezone.utc).replace(microsecond=0)
        inserted = 0
        with self._connect() as connection:
            for index, child_id in enumerate("abcdefghijklmnop"):
                special = index in {3, 10}
                category = "Kejadian" if special else ("Makan & minum" if index % 3 == 0 else "Stimulasi")
                title = "Kasus khusus perlu diperiksa" if special else ("Waktu makan dan minum" if category == "Makan & minum" else "Permainan sesuai kelompok usia")
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO daycare_activities (
                        id, child_id, child_name, category, title, note, session, time,
                        share_to_parent, announcement_json, created_by, created_at,
                        duration_minutes, mood, participation, water_ml, meal_id, meal_servings,
                        meal_snapshot_json, photo_blob, photo_content_type, media_blob, media_content_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL)""",
                    (
                        f"demo-activity-{child_id}-1", child_id, "Profil simulasi", category, title,
                        "DATA SINTETIS DEMO: catatan untuk menguji alur analitik dan bukan catatan anak nyata.",
                        ("Pagi", "Siang", "Sore")[index % 3], f"{8 + index % 4:02d}:{15 + (index % 3) * 15:02d}",
                        1 if index == 0 else 0, "demo-caregiver",
                        (now - timedelta(days=index % 7)).isoformat(timespec="seconds"),
                        10 + index % 15, "Membutuhkan dukungan" if special else "Tenang",
                        "Dengan dukungan" if index % 4 == 0 else "Mengamati",
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    @staticmethod
    def _decode_photo(data_url: str | None) -> tuple[bytes | None, str | None]:
        if not data_url:
            return None, None
        header, encoded = data_url.split(",", 1)
        content_type = header.removeprefix("data:").removesuffix(";base64")
        return base64.b64decode(encoded, validate=True), content_type

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, Any]:
        keys = set(row.keys())
        snapshot_json = row["meal_snapshot_json"] if "meal_snapshot_json" in keys else None
        photo_blob = row["photo_blob"] if "photo_blob" in keys else None
        media_blob = row["media_blob"] if "media_blob" in keys else None
        return {
            "id": row["id"],
            "child_id": row["child_id"],
            "child_name": row["child_name"],
            "category": row["category"],
            "title": row["title"],
            "note": row["note"],
            "session": row["session"],
            "time": row["time"],
            "shared": bool(row["share_to_parent"]),
            "announcement": json.loads(row["announcement_json"]) if row["announcement_json"] else None,
            "created_at": row["created_at"],
            "duration_minutes": row["duration_minutes"] if "duration_minutes" in keys else None,
            "mood": row["mood"] if "mood" in keys else None,
            "participation": row["participation"] if "participation" in keys else None,
            "water_ml": row["water_ml"] if "water_ml" in keys else None,
            "meal_id": row["meal_id"] if "meal_id" in keys else None,
            "meal_servings": row["meal_servings"] if "meal_servings" in keys else 1,
            "meal": json.loads(snapshot_json) if snapshot_json else None,
            "photo_available": bool(photo_blob),
            "media_available": bool(media_blob or photo_blob),
            "media_content_type": row["media_content_type"] if "media_content_type" in keys and row["media_content_type"] else (row["photo_content_type"] if "photo_content_type" in keys else None),
        }

    def create(
        self,
        payload: dict[str, Any],
        announcement: dict[str, Any] | None,
        created_by: str,
        meal_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        photo_blob, photo_content_type = self._decode_photo(payload.get("photo_data_url"))
        media_blob, media_content_type = self._decode_photo(payload.get("media_data_url"))
        if media_blob and media_content_type and media_content_type.startswith("video/"):
            cache_key = hashlib.sha256(media_blob).hexdigest()
            cached_media = self._normalized_media_cache.get(cache_key)
            if cached_media is None:
                cached_media = normalize_video(media_blob, media_content_type)
                self._normalized_media_cache[cache_key] = cached_media
            media_blob, media_content_type = cached_media
        if media_blob:
            photo_blob, photo_content_type = media_blob, media_content_type
        record = {
            "id": f"activity-{uuid4().hex[:12]}",
            "child_id": payload["child_id"],
            "child_name": payload["child_name"],
            "category": payload["category"],
            "title": payload["title"],
            "note": payload["note"],
            "session": payload["session"],
            "time": payload["time"],
            "shared": payload["share_to_parent"],
            "announcement": announcement,
            "created_by": created_by,
            "created_at": created_at,
            "duration_minutes": payload.get("duration_minutes"),
            "mood": payload.get("mood"),
            "participation": payload.get("participation"),
            "water_ml": payload.get("water_ml"),
            "meal_id": payload.get("meal_id") or ((payload.get("meal_items") or [{}])[0].get("meal_id")),
            "meal_servings": (payload.get("meal_items") or [{}])[0].get("servings", payload.get("meal_servings", 1)),
            "meal": meal_snapshot,
            "photo_available": bool(photo_blob),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO daycare_activities (
                    id, child_id, child_name, category, title, note, session, time,
                    share_to_parent, announcement_json, created_by, created_at,
                    duration_minutes, mood, participation, water_ml, meal_id, meal_servings,
                    meal_snapshot_json, photo_blob, photo_content_type
                    , media_blob, media_content_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"], record["child_id"], record["child_name"], record["category"],
                    record["title"], record["note"], record["session"], record["time"],
                    int(record["shared"]),
                    json.dumps(announcement, ensure_ascii=False) if announcement else None,
                    record["created_by"], created_at, record["duration_minutes"], record["mood"],
                    record["participation"], record["water_ml"], record["meal_id"],
                    record["meal_servings"],
                    json.dumps(meal_snapshot, ensure_ascii=False) if meal_snapshot else None,
                    photo_blob, photo_content_type, media_blob, media_content_type,
                ),
            )
        return record

    def list_for_user(self, role: str, child_ids: list[str]) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if role in {"caregiver", "doctor"} and child_ids:
                placeholders = ",".join("?" for _ in child_ids)
                rows = connection.execute(
                    f"SELECT * FROM daycare_activities WHERE child_id IN ({placeholders}) ORDER BY created_at DESC, rowid DESC",
                    tuple(child_ids),
                ).fetchall()
            elif role == "parent" and child_ids:
                placeholders = ",".join("?" for _ in child_ids)
                rows = connection.execute(
                    f"SELECT * FROM daycare_activities WHERE share_to_parent = 1 AND child_id IN ({placeholders}) ORDER BY created_at DESC, rowid DESC",
                    tuple(child_ids),
                ).fetchall()
            else:
                return []
        return [self._serialize(row) for row in rows]

    def get_photo(self, activity_id: str, role: str, child_ids: list[str]) -> tuple[bytes, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT id, child_id, share_to_parent, photo_blob, photo_content_type
                   FROM daycare_activities WHERE id = ?""",
                (activity_id,),
            ).fetchone()
        if row is None or not row["photo_blob"] or not row["photo_content_type"]:
            return None
        if role == "parent" and (not row["share_to_parent"] or row["child_id"] not in child_ids):
            return None
        if role in {"caregiver", "doctor"} and row["child_id"] not in child_ids:
            return None
        if role not in {"parent", "caregiver", "doctor"}:
            return None
        return bytes(row["photo_blob"]), row["photo_content_type"]
