from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class KpspRepository:
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
                CREATE TABLE IF NOT EXISTS kpsp_assessments (
                    id TEXT PRIMARY KEY,
                    child_id TEXT NOT NULL,
                    actual_age_months INTEGER NOT NULL,
                    birth_date TEXT,
                    screening_date TEXT,
                    screening_age_months INTEGER NOT NULL,
                    screening_mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    answers_json TEXT NOT NULL,
                    score_json TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    reviewed_by TEXT,
                    reviewed_at TEXT,
                    review_decision TEXT,
                    review_note TEXT,
                    published INTEGER NOT NULL DEFAULT 0,
                    published_at TEXT,
                    published_by TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            # Small additive migration for an earlier local prototype database.
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(kpsp_assessments)")}
            if "birth_date" not in columns:
                connection.execute("ALTER TABLE kpsp_assessments ADD COLUMN birth_date TEXT")
            if "screening_date" not in columns:
                connection.execute("ALTER TABLE kpsp_assessments ADD COLUMN screening_date TEXT")
            review_columns = {
                "reviewed_by": "TEXT",
                "reviewed_at": "TEXT",
                "review_decision": "TEXT",
                "review_note": "TEXT",
                "published": "INTEGER NOT NULL DEFAULT 0",
                "published_at": "TEXT",
                "published_by": "TEXT",
            }
            for column, column_type in review_columns.items():
                if column not in columns:
                    connection.execute(f"ALTER TABLE kpsp_assessments ADD COLUMN {column} {column_type}")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_kpsp_child_created ON kpsp_assessments(child_id, created_at DESC)"
            )

    def create(self, payload: dict[str, Any], score: dict[str, Any], source_version: str) -> dict[str, Any]:
        assessment_id = f"kpsp-{uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = {
            "id": assessment_id,
            "child_id": payload["child_id"],
            "actual_age_months": payload["actual_age_months"],
            "birth_date": payload.get("birth_date"),
            "screening_date": payload.get("screening_date"),
            "screening_age_months": payload["screening_age_months"],
            "screening_mode": payload["screening_mode"],
            "status": payload["status"],
            "answers": {str(key): value for key, value in payload["answers"].items()},
            "score": score,
            "source_version": source_version,
            "reviewed": False,
            "reviewed_at": None,
            "review_decision": None,
            "review_note": None,
            "published": False,
            "published_at": None,
            "created_at": created_at,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kpsp_assessments (
                    id, child_id, actual_age_months, birth_date, screening_date,
                    screening_age_months, screening_mode, status, answers_json,
                    score_json, source_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["child_id"],
                    record["actual_age_months"],
                    record["birth_date"],
                    record["screening_date"],
                    record["screening_age_months"],
                    record["screening_mode"],
                    record["status"],
                    json.dumps(record["answers"], ensure_ascii=False),
                    json.dumps(record["score"], ensure_ascii=False),
                    record["source_version"],
                    record["created_at"],
                ),
            )
        return record

    @staticmethod
    def _serialize(row: sqlite3.Row, include_answers: bool = True) -> dict[str, Any]:
        record = {
            "id": row["id"],
            "child_id": row["child_id"],
            "actual_age_months": row["actual_age_months"],
            "birth_date": row["birth_date"],
            "screening_date": row["screening_date"],
            "screening_age_months": row["screening_age_months"],
            "screening_mode": row["screening_mode"],
            "status": row["status"],
            "score": json.loads(row["score_json"]),
            "source_version": row["source_version"],
            "reviewed": bool(row["reviewed_at"]),
            "reviewed_at": row["reviewed_at"],
            "review_decision": row["review_decision"],
            "review_note": row["review_note"],
            "published": bool(row["published"]),
            "published_at": row["published_at"],
            "created_at": row["created_at"],
        }
        if include_answers:
            record["answers"] = json.loads(row["answers_json"])
        else:
            # Families only receive a short, reviewed summary; never raw KPSP answers.
            record["score"] = {
                key: record["score"].get(key)
                for key in ("result_code", "result_label", "yes_count", "total_items")
            }
        return record

    def get_by_id(self, assessment_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM kpsp_assessments WHERE id = ?",
                (assessment_id,),
            ).fetchone()
        return self._serialize(row) if row else None

    def list_for_child(self, child_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM kpsp_assessments WHERE child_id = ? ORDER BY created_at DESC",
                (child_id,),
            ).fetchall()
        return [self._serialize(row) for row in rows]

    def list_published_for_child(self, child_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM kpsp_assessments
                WHERE child_id = ? AND status = 'submitted' AND published = 1
                ORDER BY published_at DESC
                """,
                (child_id,),
            ).fetchall()
        return [self._serialize(row, include_answers=False) for row in rows]

    def save_review(self, assessment_id: str, reviewer_id: str, decision: str, note: str) -> dict[str, Any] | None:
        reviewed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE kpsp_assessments
                SET reviewed_by = ?, reviewed_at = ?, review_decision = ?, review_note = ?,
                    published = 0, published_at = NULL, published_by = NULL
                WHERE id = ? AND status = 'submitted'
                """,
                (reviewer_id, reviewed_at, decision, note, assessment_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM kpsp_assessments WHERE id = ?",
                (assessment_id,),
            ).fetchone()
        return self._serialize(row) if row else None

    def publish(self, assessment_id: str, publisher_id: str) -> dict[str, Any] | None:
        published_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE kpsp_assessments
                SET published = 1, published_at = ?, published_by = ?
                WHERE id = ? AND status = 'submitted' AND reviewed_at IS NOT NULL
                """,
                (published_at, publisher_id, assessment_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM kpsp_assessments WHERE id = ?",
                (assessment_id,),
            ).fetchone()
        return self._serialize(row) if row else None
