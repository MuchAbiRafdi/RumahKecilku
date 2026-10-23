from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class StimulationRepository:
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
                """CREATE TABLE IF NOT EXISTS stimulation_feedback (
                    id TEXT PRIMARY KEY, child_id TEXT NOT NULL, activity_id TEXT NOT NULL,
                    outcome TEXT NOT NULL, duration_minutes INTEGER, note TEXT NOT NULL,
                    created_by TEXT NOT NULL, created_at TEXT NOT NULL
                )"""
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_stimulation_feedback_child ON stimulation_feedback(child_id, created_at DESC)")

    def list_for_child(self, child_id: str, limit: int = 24) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM stimulation_feedback WHERE child_id = ? ORDER BY created_at DESC LIMIT ?",
                (child_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def create(self, child_id: str, activity_id: str, outcome: str, duration_minutes: int | None, note: str, created_by: str) -> dict[str, Any]:
        record = {
            "id": f"stimulation-feedback-{uuid4().hex[:12]}",
            "child_id": child_id,
            "activity_id": activity_id,
            "outcome": outcome,
            "duration_minutes": duration_minutes,
            "note": note,
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO stimulation_feedback (id, child_id, activity_id, outcome, duration_minutes, note, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(record.values()),
            )
        return record
