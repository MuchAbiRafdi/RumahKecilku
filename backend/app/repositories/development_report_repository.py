from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class DevelopmentReportRepository:
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
                CREATE TABLE IF NOT EXISTS development_reports (
                    id TEXT PRIMARY KEY,
                    child_id TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    observation_stats_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_by TEXT,
                    reviewed_at TEXT,
                    published_by TEXT,
                    published_at TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_development_reports_child_status ON development_reports(child_id, status, period_end DESC)"
            )

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "child_id": row["child_id"],
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "summary": row["summary"],
            "observation_stats": json.loads(row["observation_stats_json"]),
            "status": row["status"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "reviewed_by": row["reviewed_by"],
            "reviewed_at": row["reviewed_at"],
            "published_by": row["published_by"],
            "published_at": row["published_at"],
            "published": bool(row["published_at"]),
        }

    def create(
        self,
        *,
        child_id: str,
        period_start: str,
        period_end: str,
        summary: str,
        observation_stats: dict[str, Any],
        created_by: str,
    ) -> dict[str, Any]:
        record = {
            "id": f"development-report-{uuid4().hex[:12]}",
            "child_id": child_id,
            "period_start": period_start,
            "period_end": period_end,
            "summary": summary,
            "observation_stats": observation_stats,
            "status": "draft",
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reviewed_by": None,
            "reviewed_at": None,
            "published_by": None,
            "published_at": None,
            "published": False,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO development_reports (
                    id, child_id, period_start, period_end, summary, observation_stats_json,
                    status, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"], record["child_id"], record["period_start"], record["period_end"],
                    record["summary"], json.dumps(record["observation_stats"], ensure_ascii=False),
                    record["status"], record["created_by"], record["created_at"],
                ),
            )
        return record

    def list_for_user(self, role: str, child_ids: list[str]) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if role == "parent":
                if not child_ids:
                    return []
                placeholders = ",".join("?" for _ in child_ids)
                rows = connection.execute(
                    f"""SELECT * FROM development_reports
                        WHERE status = 'published' AND published_at IS NOT NULL
                          AND child_id IN ({placeholders})
                        ORDER BY period_end DESC, created_at DESC""",
                    tuple(child_ids),
                ).fetchall()
            elif role in {"caregiver", "doctor"} and child_ids:
                placeholders = ",".join("?" for _ in child_ids)
                rows = connection.execute(
                    f"SELECT * FROM development_reports WHERE child_id IN ({placeholders}) ORDER BY period_end DESC, created_at DESC",
                    tuple(child_ids),
                ).fetchall()
            else:
                return []
        return [self._serialize(row) for row in rows]

    def get_by_id(self, report_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM development_reports WHERE id = ?",
                (report_id,),
            ).fetchone()
        return self._serialize(row) if row else None

    def publish(self, report_id: str, doctor_id: str) -> dict[str, Any] | None:
        published_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE development_reports
                   SET status = 'published', reviewed_by = ?, reviewed_at = ?,
                       published_by = ?, published_at = ?
                   WHERE id = ? AND status = 'draft'""",
                (doctor_id, published_at, doctor_id, published_at, report_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM development_reports WHERE id = ?",
                (report_id,),
            ).fetchone()
        return self._serialize(row) if row else None
