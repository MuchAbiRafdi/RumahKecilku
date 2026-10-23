from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class NotificationRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS family_notifications (
                    id TEXT PRIMARY KEY,
                    recipient_id TEXT NOT NULL,
                    child_id TEXT,
                    organization_id TEXT,
                    category TEXT NOT NULL CHECK(category IN ('activity', 'photo', 'message', 'reminder')),
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    related_activity_id TEXT,
                    related_message_id TEXT,
                    due_at TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    read_at TEXT,
                    completed_at TEXT,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    FOREIGN KEY(recipient_id) REFERENCES auth_users(id) ON DELETE CASCADE
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(family_notifications)")}
            if "organization_id" not in columns:
                connection.execute("ALTER TABLE family_notifications ADD COLUMN organization_id TEXT")
            connection.execute(
                """UPDATE family_notifications SET organization_id = (
                       SELECT MIN(organization_id) FROM organization_memberships
                       WHERE user_id = family_notifications.created_by AND status = 'active'
                       GROUP BY user_id HAVING COUNT(*) = 1
                   ) WHERE child_id IS NULL AND organization_id IS NULL"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_family_notifications_recipient_created ON family_notifications(recipient_id, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_family_notifications_org_created ON family_notifications(organization_id, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_family_notifications_due ON family_notifications(recipient_id, due_at)"
            )

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "child_id": row["child_id"],
            "organization_id": row["organization_id"] if "organization_id" in row.keys() else None,
            "category": row["category"],
            "title": row["title"],
            "body": row["body"],
            "related_activity_id": row["related_activity_id"],
            "related_message_id": row["related_message_id"],
            "due_at": row["due_at"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "read_at": row["read_at"],
            "completed_at": row["completed_at"],
            "is_read": bool(row["read_at"]),
            "is_completed": bool(row["completed_at"]),
        }

    def create_for_recipients(
        self,
        *,
        recipient_ids: list[str],
        child_id: str | None,
        category: str,
        organization_id: str | None = None,
        title: str,
        body: str,
        created_by: str,
        dedupe_key: str | None = None,
        related_activity_id: str | None = None,
        related_message_id: str | None = None,
        due_at: str | None = None,
    ) -> list[dict[str, Any]]:
        unique_recipients = list(dict.fromkeys(recipient_ids))
        if not unique_recipients:
            return []
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records: list[dict[str, Any]] = []
        with self._connect() as connection:
            if organization_id is None and child_id:
                owner = connection.execute(
                    "SELECT organization_id FROM child_profiles WHERE id = ? AND status = 'active'",
                    (child_id,),
                ).fetchone()
                organization_id = owner["organization_id"] if owner else None
            for recipient_id in unique_recipients:
                current_dedupe_key = f"{dedupe_key}:{recipient_id}" if dedupe_key else f"manual:{uuid4().hex}"
                notification_id = f"notification-{uuid4().hex[:12]}"
                connection.execute(
                    """
                    INSERT OR IGNORE INTO family_notifications (
                        id, recipient_id, child_id, organization_id, category, title, body,
                        related_activity_id, related_message_id, due_at, created_by,
                        created_at, dedupe_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        notification_id, recipient_id, child_id, organization_id, category, title.strip(), body.strip(),
                        related_activity_id, related_message_id, due_at, created_by,
                        created_at, current_dedupe_key,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM family_notifications WHERE dedupe_key = ?",
                    (current_dedupe_key,),
                ).fetchone()
                if row is not None:
                    records.append(self._serialize(row))
        return records

    def list_for_user(
        self,
        user_id: str,
        role: str,
        child_ids: list[str],
        organization_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        organization_ids = organization_ids or []
        clauses: list[str] = []
        parameters: list[str] = [user_id]
        if child_ids:
            placeholders = ",".join("?" for _ in child_ids)
            clauses.append(f"child_id IN ({placeholders})")
            parameters.extend(child_ids)
        if organization_ids:
            placeholders = ",".join("?" for _ in organization_ids)
            clauses.append(f"(child_id IS NULL AND organization_id IN ({placeholders}))")
            parameters.extend(organization_ids)
        if not clauses:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT * FROM family_notifications WHERE recipient_id = ? AND ({' OR '.join(clauses)})
                    ORDER BY created_at DESC LIMIT 100""",
                tuple(parameters),
            ).fetchall()
        return [self._serialize(row) for row in rows]

    @staticmethod
    def _scope(child_ids: list[str], organization_ids: list[str]) -> tuple[str, tuple[str, ...]]:
        clauses: list[str] = []
        parameters: list[str] = []
        if child_ids:
            placeholders = ",".join("?" for _ in child_ids)
            clauses.append(f"child_id IN ({placeholders})")
            parameters.extend(child_ids)
        if organization_ids:
            placeholders = ",".join("?" for _ in organization_ids)
            clauses.append(f"(child_id IS NULL AND organization_id IN ({placeholders}))")
            parameters.extend(organization_ids)
        return (f"({' OR '.join(clauses)})" if clauses else "1 = 0", tuple(parameters))

    def mark_read(
        self,
        notification_id: str,
        user_id: str,
        child_ids: list[str],
        organization_ids: list[str],
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        scope, scope_parameters = self._scope(child_ids, organization_ids)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE family_notifications SET read_at = COALESCE(read_at, ?) WHERE id = ? AND recipient_id = ? AND {scope}",
                (now, notification_id, user_id, *scope_parameters),
            )
            row = connection.execute(
                f"SELECT * FROM family_notifications WHERE id = ? AND recipient_id = ? AND {scope}",
                (notification_id, user_id, *scope_parameters),
            ).fetchone()
        return self._serialize(row) if row else None

    def complete_reminder(
        self,
        notification_id: str,
        user_id: str,
        child_ids: list[str],
        organization_ids: list[str],
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        scope, scope_parameters = self._scope(child_ids, organization_ids)
        with self._connect() as connection:
            connection.execute(
                f"""UPDATE family_notifications
                   SET completed_at = COALESCE(completed_at, ?), read_at = COALESCE(read_at, ?)
                   WHERE id = ? AND recipient_id = ? AND category = 'reminder' AND {scope}""",
                (now, now, notification_id, user_id, *scope_parameters),
            )
            row = connection.execute(
                f"SELECT * FROM family_notifications WHERE id = ? AND recipient_id = ? AND category = 'reminder' AND {scope}",
                (notification_id, user_id, *scope_parameters),
            ).fetchone()
        return self._serialize(row) if row else None
