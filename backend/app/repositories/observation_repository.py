from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class ObservationRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS milestone_observations (
                    id TEXT PRIMARY KEY,
                    child_id TEXT NOT NULL,
                    aspect TEXT NOT NULL,
                    milestone TEXT NOT NULL DEFAULT '',
                    reference TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL,
                    context TEXT NOT NULL,
                    note TEXT NOT NULL,
                    time TEXT NOT NULL,
                    observer TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(milestone_observations)")}
            if "milestone" not in columns:
                connection.execute("ALTER TABLE milestone_observations ADD COLUMN milestone TEXT NOT NULL DEFAULT ''")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_observation_child_created ON milestone_observations(child_id, created_at DESC)"
            )

    def seed_demo_samples(self) -> int:
        """Insert clearly marked, idempotent observations for the synthetic preview only."""
        now = datetime.now(timezone.utc).replace(microsecond=0)
        samples = (
            ("demo-observation-a-language-1", "a", "Bahasa", "Menunjuk ilustrasi setelah diajak melihat buku", "Teramati", "Membaca buku bergambar bersama", "Menunjuk satu ilustrasi ketika pengasuh menyebut gambar.", 14, "09:15"),
            ("demo-observation-a-language-2", "a", "Bahasa", "Menggunakan gestur saat berbincang", "Teramati", "Percakapan saat bermain bersama", "Mengarah ke benda yang disebut dalam percakapan.", 5, "10:05"),
            ("demo-observation-a-fine-1", "a", "Motorik halus", "Memindahkan balok besar ke wadah", "Teramati", "Balok besar di alas bermain", "Memindahkan dua balok besar ke wadah terbuka setelah diajak.", 9, "09:40"),
            ("demo-observation-a-social-1", "a", "Sosial-emosional", "Menunggu giliran dalam permainan singkat", "Belum teramati", "Permainan bergiliran dengan pengasuh", "Dalam kesempatan ini perilaku sasaran belum terlihat; catatan ini tidak menyimpulkan kemampuan.", 2, "10:20"),
            ("demo-observation-b-language-1", "b", "Bahasa", "Merespons ajakan melihat gambar", "Belum teramati", "Buku bergambar setelah waktu istirahat", "Dalam kesempatan ini respons sasaran belum terlihat; kesempatan dan kondisi dicatat untuk ditinjau.", 12, "09:30"),
            ("demo-observation-b-language-2", "b", "Bahasa", "Merespons ajakan melihat gambar", "Belum teramati", "Buku bergambar di ruang bermain", "Pada konteks berbeda ini respons sasaran juga belum terlihat; bukan kesimpulan tentang kemampuan.", 3, "10:10"),
            ("demo-observation-c-gross-1", "c", "Motorik kasar", "Bergerak menuju benda pilihan di alas bermain", "Teramati", "Alas bermain yang lapang", "Bergerak menuju benda pilihan ketika diletakkan dekat.", 10, "09:50"),
            ("demo-observation-c-gross-2", "c", "Motorik kasar", "Bergerak menuju benda pilihan di alas bermain", "Teramati", "Bermain bebas dengan pengasuh", "Bergerak menuju benda pilihan; pengasuh berada dekat untuk mendampingi.", 4, "09:45"),
            ("demo-observation-e-fine-1", "e", "Motorik halus", "Memindahkan benda besar ke wadah", "Belum ada kesempatan", "Sesi membaca dan mendengarkan cerita", "Kegiatan sesi ini tidak memberi kesempatan mengamati perilaku sasaran.", 6, "09:25"),
        )
        # Add one age-band coverage sample for every synthetic profile so the preview
        # can exercise analytics and recommendation loading across the full KPSP range.
        coverage_aspects = ("Motorik kasar", "Motorik halus", "Bahasa", "Sosial-emosional")
        coverage_samples = tuple(
            (
                f"demo-observation-{child_id}-coverage-1",
                child_id,
                coverage_aspects[index % len(coverage_aspects)],
                "Mengikuti kegiatan sesuai kesempatan yang diberikan",
                "Teramati" if index % 3 else "Belum ada kesempatan",
                "Sesi simulasi sesuai kelompok usia",
                "DATA SINTETIS DEMO: perilaku dicatat untuk menguji alur analitik; bukan penilaian kemampuan anak.",
                index + 1,
                f"{9 + index % 3:02d}:{15 + index % 4 * 10:02d}",
            )
            for index, child_id in enumerate("abcdefghijklmnop")
        )
        samples = samples + coverage_samples
        inserted = 0
        with self._connect() as connection:
            for row_id, child_id, aspect, milestone, result, context, note, age_days, time in samples:
                created_at = (now - timedelta(days=age_days)).isoformat(timespec="seconds")
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO milestone_observations (
                        id, child_id, aspect, milestone, reference, result, context, note,
                        time, observer, created_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row_id,
                        child_id,
                        aspect,
                        milestone,
                        "DEMO-SINTETIS",
                        result,
                        f"DEMO SINTETIS · {context}",
                        f"DATA SINTETIS DEMO: {note}",
                        time,
                        "Rani · Pengasuh demo",
                        "demo-caregiver",
                        created_at,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def create(self, payload: dict[str, Any], observer: str, created_by: str) -> dict[str, Any]:
        record = {
            "id": f"observation-{uuid4().hex[:12]}",
            "child_id": payload["child_id"],
            "aspect": payload["aspect"],
            "milestone": payload.get("milestone", ""),
            "reference": payload.get("reference", ""),
            "result": payload["result"],
            "context": payload["context"],
            "note": payload["note"],
            "time": payload["time"],
            "observer": observer,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO milestone_observations (
                    id, child_id, aspect, milestone, reference, result, context, note,
                    time, observer, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"], record["child_id"], record["aspect"], record["milestone"],
                    record["reference"], record["result"], record["context"], record["note"],
                    record["time"], record["observer"], record["created_by"], record["created_at"],
                ),
            )
        return record

    def list_for_user(self, role: str, child_ids: list[str]) -> list[dict[str, Any]]:
        if role not in {"caregiver", "doctor"} or not child_ids:
            return []
        placeholders = ",".join("?" for _ in child_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM milestone_observations WHERE child_id IN ({placeholders}) ORDER BY created_at DESC, rowid DESC",
                tuple(child_ids),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "child_id": row["child_id"],
                "aspect": row["aspect"],
                "milestone": row["milestone"],
                "reference": row["reference"],
                "result": row["result"],
                "context": row["context"],
                "note": row["note"],
                "time": row["time"],
                "observer": row["observer"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
