from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo


LOCAL_TZ = ZoneInfo("Asia/Jakarta")


class MessageRepository:
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
                CREATE TABLE IF NOT EXISTS family_messages (
                    id TEXT PRIMARY KEY,
                    child_id TEXT,
                    organization_id TEXT,
                    author TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('caregiver', 'parent')),
                    text TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('Pengumuman', 'Balasan')),
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(family_messages)")}
            if "organization_id" not in columns:
                connection.execute("ALTER TABLE family_messages ADD COLUMN organization_id TEXT")
            # Attribute legacy tenant-wide notices only when their sender has exactly one
            # active organization. Ambiguous legacy rows remain hidden until reviewed.
            connection.execute(
                """UPDATE family_messages SET organization_id = (
                       SELECT MIN(organization_id) FROM organization_memberships
                       WHERE user_id = family_messages.created_by AND status = 'active'
                       GROUP BY user_id HAVING COUNT(*) = 1
                   ) WHERE child_id IS NULL AND organization_id IS NULL"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_family_messages_child_created ON family_messages(child_id, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_family_messages_org_created ON family_messages(organization_id, created_at DESC)"
            )
            # New direct threads live in a separate table so existing family_messages are preserved.
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS direct_chat_messages (
                    id TEXT PRIMARY KEY,
                    child_id TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    sender_name TEXT NOT NULL,
                    sender_role TEXT NOT NULL CHECK(sender_role IN ('parent', 'caregiver', 'doctor')),
                    recipient_id TEXT NOT NULL,
                    recipient_name TEXT NOT NULL,
                    recipient_role TEXT NOT NULL CHECK(recipient_role IN ('parent', 'caregiver', 'doctor')),
                    text TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    related_activity_id TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_direct_chat_sender_created ON direct_chat_messages(sender_id, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_direct_chat_recipient_created ON direct_chat_messages(recipient_id, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_direct_chat_child_created ON direct_chat_messages(child_id, created_at DESC)"
            )

    @staticmethod
    def _timestamp(now: datetime) -> str:
        return now.isoformat(timespec="seconds")

    @staticmethod
    def _local_time(created_at: str) -> str:
        return datetime.fromisoformat(created_at).astimezone(LOCAL_TZ).strftime("%H:%M")

    def create(
        self,
        *,
        child_id: str | None,
        author: str,
        role: str,
        organization_id: str | None = None,
        text: str,
        created_by: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        record = {
            "id": f"message-{uuid4().hex[:12]}",
            "child_id": child_id,
            "organization_id": organization_id,
            "author": author,
            "role": role,
            "text": text,
            "kind": "Pengumuman" if role == "caregiver" else "Balasan",
            "created_at": self._timestamp(now),
            "time": now.astimezone(LOCAL_TZ).strftime("%H:%M"),
            "sender_id": created_by,
            "recipient_id": None,
            "related_activity_id": None,
            "is_direct": False,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO family_messages (id, child_id, organization_id, author, role, text, kind, created_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"], child_id, organization_id, author, role, text,
                    record["kind"], record["created_at"], created_by,
                ),
            )
        return record

    def create_direct_message(
        self,
        *,
        child_id: str,
        sender: dict[str, str],
        recipient: dict[str, str],
        text: str,
        kind: str = "Pesan langsung",
        related_activity_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        record = {
            "id": f"message-{uuid4().hex[:12]}",
            "child_id": child_id,
            "sender_id": sender["id"],
            "sender_name": sender["name"],
            "sender_role": sender["role"],
            "recipient_id": recipient["id"],
            "recipient_name": recipient["name"],
            "recipient_role": recipient["role"],
            "author": sender["name"],
            "role": sender["role"],
            "text": text,
            "kind": kind,
            "created_at": self._timestamp(now),
            "time": now.astimezone(LOCAL_TZ).strftime("%H:%M"),
            "related_activity_id": related_activity_id,
            "is_direct": True,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO direct_chat_messages (
                    id, child_id, sender_id, sender_name, sender_role,
                    recipient_id, recipient_name, recipient_role, text, kind,
                    created_at, created_by, related_activity_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"], child_id, sender["id"], sender["name"], sender["role"],
                    recipient["id"], recipient["name"], recipient["role"], text, kind,
                    record["created_at"], sender["id"], related_activity_id,
                ),
            )
        return record

    def create_event_for_recipients(
        self,
        *,
        child_id: str,
        sender: dict[str, str],
        recipients: list[dict[str, str]],
        text: str,
        kind: str,
        related_activity_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            self.create_direct_message(
                child_id=child_id,
                sender=sender,
                recipient=recipient,
                text=text,
                kind=kind,
                related_activity_id=related_activity_id,
            )
            for recipient in recipients
            if recipient["id"] != sender["id"]
        ]

    def list_for_user(
        self,
        role: str,
        child_ids: list[str],
        user_id: str,
        child_filter: str | None = None,
        organization_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        legacy_rows: list[sqlite3.Row] = []
        direct_rows: list[sqlite3.Row] = []
        organization_ids = organization_ids or []
        with self._connect() as connection:
            allowed_ids = [item for item in child_ids if not child_filter or item == child_filter]
            if role == "caregiver" and allowed_ids:
                child_placeholders = ",".join("?" for _ in allowed_ids)
                if organization_ids:
                    org_placeholders = ",".join("?" for _ in organization_ids)
                    legacy_rows = connection.execute(
                        f"""SELECT * FROM family_messages
                            WHERE child_id IN ({child_placeholders})
                               OR (child_id IS NULL AND organization_id IN ({org_placeholders}))
                            ORDER BY created_at DESC LIMIT 300""",
                        (*allowed_ids, *organization_ids),
                    ).fetchall()
                else:
                    legacy_rows = connection.execute(
                        f"""SELECT * FROM family_messages WHERE child_id IN ({child_placeholders})
                            ORDER BY created_at DESC LIMIT 300""",
                        tuple(allowed_ids),
                    ).fetchall()
            elif role == "parent" and allowed_ids:
                child_placeholders = ",".join("?" for _ in allowed_ids)
                if organization_ids:
                    org_placeholders = ",".join("?" for _ in organization_ids)
                    legacy_rows = connection.execute(
                        f"""SELECT * FROM family_messages
                            WHERE child_id IN ({child_placeholders})
                               OR (child_id IS NULL AND organization_id IN ({org_placeholders}))
                            ORDER BY created_at DESC LIMIT 300""",
                        (*allowed_ids, *organization_ids),
                    ).fetchall()
                else:
                    legacy_rows = connection.execute(
                        f"""SELECT * FROM family_messages WHERE child_id IN ({child_placeholders})
                            ORDER BY created_at DESC LIMIT 300""",
                        tuple(allowed_ids),
                    ).fetchall()

            direct_parameters: list[str] = [user_id, user_id]
            direct_query = """SELECT * FROM direct_chat_messages
                              WHERE (sender_id = ? OR recipient_id = ?)"""
            if not allowed_ids:
                direct_query += " AND 1 = 0"
            else:
                placeholders = ",".join("?" for _ in allowed_ids)
                direct_query += f" AND child_id IN ({placeholders})"
                direct_parameters.extend(allowed_ids)
            direct_query += " ORDER BY created_at DESC LIMIT 500"
            direct_rows = connection.execute(direct_query, tuple(direct_parameters)).fetchall()

        messages: list[dict[str, Any]] = []
        for row in legacy_rows:
            child_id = row["child_id"]
            if child_filter and child_id not in {None, child_filter}:
                continue
            messages.append({
                "id": row["id"],
                "child_id": child_id,
                "author": row["author"],
                "role": row["role"],
                "sender_id": row["created_by"],
                "recipient_id": None,
                "recipient_name": None,
                "recipient_role": None,
                "text": row["text"],
                "kind": row["kind"],
                "time": self._local_time(row["created_at"]),
                "created_at": row["created_at"],
                "related_activity_id": None,
                "is_direct": False,
            })
        for row in direct_rows:
            messages.append({
                "id": row["id"],
                "child_id": row["child_id"],
                "author": row["sender_name"],
                "role": row["sender_role"],
                "sender_id": row["sender_id"],
                "recipient_id": row["recipient_id"],
                "recipient_name": row["recipient_name"],
                "recipient_role": row["recipient_role"],
                "text": row["text"],
                "kind": row["kind"],
                "time": self._local_time(row["created_at"]),
                "created_at": row["created_at"],
                "related_activity_id": row["related_activity_id"],
                "is_direct": True,
            })
        messages.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
        return messages[:500]
