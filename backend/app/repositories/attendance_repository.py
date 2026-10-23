from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo


LOCAL_ZONE = ZoneInfo("Asia/Jakarta")


class AttendanceRepository:
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
                CREATE TABLE IF NOT EXISTS child_attendance (
                    child_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('Hadir', 'Izin', 'Sakit')),
                    check_in TEXT,
                    updated_at TEXT NOT NULL,
                    updated_by TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS authorized_pickups (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('active', 'revoked')),
                    parent_confirmation_method TEXT NOT NULL CHECK(parent_confirmation_method IN ('in_person', 'phone', 'offline_written_record')),
                    parent_confirmation_recorded_by TEXT NOT NULL,
                    parent_confirmation_recorded_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_by TEXT,
                    revoked_at TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_authorized_pickups_child_status ON authorized_pickups(child_id, status, created_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS attendance_sessions (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('Hadir', 'Izin', 'Sakit')),
                    check_in_at TEXT,
                    check_in_by TEXT,
                    check_out_at TEXT,
                    check_out_by TEXT,
                    pickup_authorization_id TEXT,
                    pickup_person_name TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(child_id, local_date)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_attendance_sessions_date_child ON attendance_sessions(local_date, child_id)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS attendance_events (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK(event_type IN ('authorized_pickup_added', 'authorized_pickup_revoked', 'check_in', 'check_out', 'status_marked')),
                    status TEXT,
                    actor_user_id TEXT NOT NULL,
                    pickup_authorization_id TEXT,
                    pickup_person_name TEXT,
                    parent_confirmation_method TEXT,
                    pickup_name_match_confirmed INTEGER NOT NULL DEFAULT 0,
                    occurred_at TEXT NOT NULL
                )
                """
            )
            event_columns = {row["name"] for row in connection.execute("PRAGMA table_info(attendance_events)")}
            if "pickup_name_match_confirmed" not in event_columns:
                connection.execute("ALTER TABLE attendance_events ADD COLUMN pickup_name_match_confirmed INTEGER NOT NULL DEFAULT 0")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_attendance_events_child_created ON attendance_events(child_id, occurred_at DESC)"
            )
            legacy_rows = connection.execute(
                """SELECT attendance.child_id, attendance.status, attendance.check_in,
                          attendance.updated_at, attendance.updated_by, child.organization_id
                   FROM child_attendance AS attendance
                   JOIN child_profiles AS child ON child.id = attendance.child_id
                   JOIN daycare_organizations AS organization ON organization.id = child.organization_id
                   WHERE child.status = 'active' AND organization.status = 'active'"""
            ).fetchall()
            for row in legacy_rows:
                try:
                    updated_at = datetime.fromisoformat(row["updated_at"])
                    local_date = updated_at.astimezone(LOCAL_ZONE).date().isoformat()
                except (TypeError, ValueError):
                    continue
                check_in_at = row["updated_at"] if row["status"] == "Hadir" and row["check_in"] else None
                connection.execute(
                    """INSERT OR IGNORE INTO attendance_sessions
                       (id, organization_id, child_id, local_date, status, check_in_at, check_in_by,
                        updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (f"attendance-session-legacy-{uuid4().hex[:12]}", row["organization_id"],
                     row["child_id"], local_date, row["status"], check_in_at,
                     row["updated_by"] if check_in_at else None, row["updated_at"]),
                )

    @staticmethod
    def _now() -> tuple[datetime, datetime, str, str]:
        now = datetime.now(timezone.utc)
        local_now = now.astimezone(LOCAL_ZONE)
        return now, local_now, now.isoformat(timespec="seconds"), local_now.date().isoformat()

    @staticmethod
    def _time_label(value: str | None) -> str:
        if not value:
            return "Belum dicatat"
        try:
            return datetime.fromisoformat(value).astimezone(LOCAL_ZONE).strftime("%H.%M")
        except ValueError:
            return value

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        *,
        organization_id: str,
        child_id: str,
        local_date: str,
        event_type: str,
        actor_user_id: str,
        occurred_at: str,
        status: str | None = None,
        pickup_authorization_id: str | None = None,
        pickup_person_name: str | None = None,
        parent_confirmation_method: str | None = None,
        pickup_name_match_confirmed: bool = False,
    ) -> None:
        connection.execute(
            """INSERT INTO attendance_events
               (id, organization_id, child_id, local_date, event_type, status, actor_user_id,
                pickup_authorization_id, pickup_person_name, parent_confirmation_method,
                pickup_name_match_confirmed, occurred_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (f"attendance-event-{uuid4().hex[:16]}", organization_id, child_id, local_date,
             event_type, status, actor_user_id, pickup_authorization_id, pickup_person_name,
             parent_confirmation_method, int(pickup_name_match_confirmed), occurred_at),
        )

    @staticmethod
    def _active_child_organization(
        connection: sqlite3.Connection, child_id: str, organization_id: str
    ) -> bool:
        row = connection.execute(
            """SELECT 1 FROM child_profiles AS child
               JOIN daycare_organizations AS organization ON organization.id = child.organization_id
               WHERE child.id = ? AND child.organization_id = ?
                 AND child.status = 'active' AND organization.status = 'active'""",
            (child_id, organization_id),
        ).fetchone()
        return row is not None

    def update(self, child_id: str, status: str, updated_by: str) -> dict[str, Any]:
        now, local_now, updated_at, local_date = self._now()
        check_in = local_now.strftime("%H.%M") if status == "Hadir" else None
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            child = connection.execute(
                "SELECT organization_id FROM child_profiles WHERE id = ? AND status = 'active'",
                (child_id,),
            ).fetchone()
            if child is None:
                raise LookupError("Profil anak aktif tidak ditemukan.")
            organization_id = child["organization_id"]
            existing_session = connection.execute(
                "SELECT check_in_at FROM attendance_sessions WHERE child_id = ? AND local_date = ?",
                (child_id, local_date),
            ).fetchone()
            if status != "Hadir" and existing_session and existing_session["check_in_at"]:
                raise FileExistsError("Anak sudah check-in; catat proses check-out, bukan status izin/sakit.")
            connection.execute(
                """
                INSERT INTO child_attendance (child_id, status, check_in, updated_at, updated_by)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(child_id) DO UPDATE SET
                    status = excluded.status,
                    check_in = excluded.check_in,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (child_id, status, check_in, updated_at, updated_by),
            )
            session = connection.execute(
                "SELECT id FROM attendance_sessions WHERE child_id = ? AND local_date = ?",
                (child_id, local_date),
            ).fetchone()
            session_id = session["id"] if session else f"attendance-session-{uuid4().hex[:16]}"
            connection.execute(
                """INSERT INTO attendance_sessions
                   (id, organization_id, child_id, local_date, status, check_in_at, check_in_by,
                    updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(child_id, local_date) DO UPDATE SET
                     status = excluded.status,
                     check_in_at = CASE WHEN excluded.status = 'Hadir'
                                        THEN COALESCE(attendance_sessions.check_in_at, excluded.check_in_at)
                                        ELSE attendance_sessions.check_in_at END,
                     check_in_by = CASE WHEN excluded.status = 'Hadir'
                                        THEN COALESCE(attendance_sessions.check_in_by, excluded.check_in_by)
                                        ELSE attendance_sessions.check_in_by END,
                     updated_at = excluded.updated_at""",
                (session_id, organization_id, child_id, local_date, status,
                 updated_at if status == "Hadir" else None, updated_by if status == "Hadir" else None, updated_at),
            )
            self._event(
                connection,
                organization_id=organization_id,
                child_id=child_id,
                local_date=local_date,
                event_type="status_marked",
                actor_user_id=updated_by,
                occurred_at=updated_at,
                status=status,
            )
        return {
            "child_id": child_id,
            "status": status,
            "check_in": check_in or "Belum dicatat",
            "check_out": "Belum dicatat",
            "pickup_person_name": None,
            "updated_at": updated_at,
        }

    def create_authorized_pickup(
        self,
        *,
        organization_id: str,
        child_id: str,
        name: str,
        relationship: str,
        parent_confirmation_method: str,
        admin_user_id: str,
    ) -> dict[str, Any]:
        now, _, created_at, local_date = self._now()
        normalized_name = " ".join(name.split())
        normalized_relationship = " ".join(relationship.split())
        pickup_id = f"pickup-{uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not self._active_child_organization(connection, child_id, organization_id):
                raise LookupError("Profil anak aktif tidak ditemukan pada daycare ini.")
            duplicate = connection.execute(
                """SELECT id FROM authorized_pickups
                   WHERE organization_id = ? AND child_id = ? AND status = 'active'
                     AND name = ? COLLATE NOCASE""",
                (organization_id, child_id, normalized_name),
            ).fetchone()
            if duplicate:
                raise FileExistsError("Penjemput aktif dengan nama yang sama sudah terdaftar untuk profil ini.")
            connection.execute(
                """INSERT INTO authorized_pickups
                   (id, organization_id, child_id, name, relationship, status,
                    parent_confirmation_method, parent_confirmation_recorded_by,
                    parent_confirmation_recorded_at, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)""",
                (pickup_id, organization_id, child_id, normalized_name, normalized_relationship,
                 parent_confirmation_method, admin_user_id, created_at, admin_user_id, created_at),
            )
            self._event(
                connection,
                organization_id=organization_id,
                child_id=child_id,
                local_date=local_date,
                event_type="authorized_pickup_added",
                actor_user_id=admin_user_id,
                occurred_at=created_at,
                pickup_authorization_id=pickup_id,
                pickup_person_name=normalized_name,
                parent_confirmation_method=parent_confirmation_method,
            )
            record = connection.execute(
                """SELECT id, child_id, name, relationship, status,
                          parent_confirmation_method, parent_confirmation_recorded_at, created_at
                   FROM authorized_pickups WHERE id = ?""",
                (pickup_id,),
            ).fetchone()
        return dict(record)

    def list_authorized_pickups(self, *, organization_id: str, child_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if not self._active_child_organization(connection, child_id, organization_id):
                return []
            rows = connection.execute(
                """SELECT id, child_id, name, relationship, status, parent_confirmation_method,
                          parent_confirmation_recorded_at, created_at
                   FROM authorized_pickups
                   WHERE organization_id = ? AND child_id = ? AND status = 'active'
                   ORDER BY name COLLATE NOCASE, id""",
                (organization_id, child_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def revoke_authorized_pickup(
        self,
        *,
        organization_id: str,
        child_id: str,
        pickup_id: str,
        admin_user_id: str,
    ) -> dict[str, Any] | None:
        _, _, revoked_at, local_date = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not self._active_child_organization(connection, child_id, organization_id):
                return None
            pickup = connection.execute(
                """SELECT id, name, relationship, parent_confirmation_method
                   FROM authorized_pickups
                   WHERE id = ? AND child_id = ? AND organization_id = ? AND status = 'active'""",
                (pickup_id, child_id, organization_id),
            ).fetchone()
            if pickup is None:
                return None
            connection.execute(
                """UPDATE authorized_pickups SET status = 'revoked', revoked_by = ?, revoked_at = ?
                   WHERE id = ? AND child_id = ? AND organization_id = ? AND status = 'active'""",
                (admin_user_id, revoked_at, pickup_id, child_id, organization_id),
            )
            self._event(
                connection,
                organization_id=organization_id,
                child_id=child_id,
                local_date=local_date,
                event_type="authorized_pickup_revoked",
                actor_user_id=admin_user_id,
                occurred_at=revoked_at,
                pickup_authorization_id=pickup_id,
                pickup_person_name=pickup["name"],
                parent_confirmation_method=pickup["parent_confirmation_method"],
            )
        return {"id": pickup["id"], "name": pickup["name"], "relationship": pickup["relationship"], "status": "revoked", "revoked_at": revoked_at}

    def check_in(self, *, organization_id: str, child_id: str, actor_user_id: str) -> dict[str, Any]:
        _, local_now, occurred_at, local_date = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not self._active_child_organization(connection, child_id, organization_id):
                raise LookupError("Profil anak aktif tidak ditemukan pada daycare ini.")
            existing = connection.execute(
                "SELECT check_in_at, check_out_at FROM attendance_sessions WHERE child_id = ? AND local_date = ?",
                (child_id, local_date),
            ).fetchone()
            if existing and existing["check_in_at"]:
                raise FileExistsError("Check-in hari ini sudah tercatat.")
            session_id = f"attendance-session-{uuid4().hex[:16]}"
            connection.execute(
                """INSERT INTO attendance_sessions
                   (id, organization_id, child_id, local_date, status, check_in_at, check_in_by,
                    check_out_at, check_out_by, pickup_authorization_id, pickup_person_name, updated_at)
                   VALUES (?, ?, ?, ?, 'Hadir', ?, ?, NULL, NULL, NULL, NULL, ?)
                   ON CONFLICT(child_id, local_date) DO UPDATE SET
                     status = 'Hadir', check_in_at = excluded.check_in_at,
                     check_in_by = excluded.check_in_by, check_out_at = NULL,
                     check_out_by = NULL, pickup_authorization_id = NULL,
                     pickup_person_name = NULL, updated_at = excluded.updated_at""",
                (session_id, organization_id, child_id, local_date, occurred_at, actor_user_id, occurred_at),
            )
            check_in = local_now.strftime("%H.%M")
            connection.execute(
                """INSERT INTO child_attendance (child_id, status, check_in, updated_at, updated_by)
                   VALUES (?, 'Hadir', ?, ?, ?)
                   ON CONFLICT(child_id) DO UPDATE SET status = 'Hadir', check_in = excluded.check_in,
                     updated_at = excluded.updated_at, updated_by = excluded.updated_by""",
                (child_id, check_in, occurred_at, actor_user_id),
            )
            self._event(
                connection,
                organization_id=organization_id,
                child_id=child_id,
                local_date=local_date,
                event_type="check_in",
                actor_user_id=actor_user_id,
                occurred_at=occurred_at,
                status="Hadir",
            )
        return {"child_id": child_id, "status": "Hadir", "check_in": check_in, "check_out": "Belum dicatat", "pickup_person_name": None, "updated_at": occurred_at}

    def check_out(
        self,
        *,
        organization_id: str,
        child_id: str,
        pickup_authorization_id: str,
        actor_user_id: str,
    ) -> dict[str, Any]:
        _, local_now, occurred_at, local_date = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not self._active_child_organization(connection, child_id, organization_id):
                raise LookupError("Profil anak aktif tidak ditemukan pada daycare ini.")
            session = connection.execute(
                """SELECT id, check_in_at, check_out_at FROM attendance_sessions
                   WHERE organization_id = ? AND child_id = ? AND local_date = ?""",
                (organization_id, child_id, local_date),
            ).fetchone()
            if session is None or not session["check_in_at"]:
                raise FileExistsError("Catat check-in sebelum proses check-out.")
            if session["check_out_at"]:
                raise FileExistsError("Check-out hari ini sudah tercatat.")
            pickup = connection.execute(
                """SELECT id, name FROM authorized_pickups
                   WHERE id = ? AND organization_id = ? AND child_id = ? AND status = 'active'""",
                (pickup_authorization_id, organization_id, child_id),
            ).fetchone()
            if pickup is None:
                raise LookupError("Nama penjemput aktif yang dipilih tidak ditemukan untuk profil ini.")
            connection.execute(
                """UPDATE attendance_sessions SET check_out_at = ?, check_out_by = ?,
                     pickup_authorization_id = ?, pickup_person_name = ?, updated_at = ?
                   WHERE id = ? AND check_out_at IS NULL""",
                (occurred_at, actor_user_id, pickup["id"], pickup["name"], occurred_at, session["id"]),
            )
            check_in_row = connection.execute(
                "SELECT check_in_at FROM attendance_sessions WHERE id = ?", (session["id"],)
            ).fetchone()
            connection.execute(
                """INSERT INTO child_attendance (child_id, status, check_in, updated_at, updated_by)
                   VALUES (?, 'Hadir', ?, ?, ?)
                   ON CONFLICT(child_id) DO UPDATE SET status = 'Hadir',
                     check_in = excluded.check_in, updated_at = excluded.updated_at,
                     updated_by = excluded.updated_by""",
                (child_id, self._time_label(check_in_row["check_in_at"]), occurred_at, actor_user_id),
            )
            self._event(
                connection,
                organization_id=organization_id,
                child_id=child_id,
                local_date=local_date,
                event_type="check_out",
                actor_user_id=actor_user_id,
                occurred_at=occurred_at,
                status="Hadir",
                pickup_authorization_id=pickup["id"],
                pickup_person_name=pickup["name"],
                pickup_name_match_confirmed=True,
            )
        return {"child_id": child_id, "status": "Hadir", "check_in": self._time_label(check_in_row["check_in_at"]), "check_out": local_now.strftime("%H.%M"), "pickup_person_name": pickup["name"], "pickup_name_match_confirmed": True, "updated_at": occurred_at}

    def list_for_user(self, role: str, child_ids: list[str]) -> list[dict[str, Any]]:
        if role not in {"caregiver", "doctor", "admin", "parent"} or not child_ids:
            return []
        _, _, _, local_date = self._now()
        placeholders = ",".join("?" for _ in child_ids)
        with self._connect() as connection:
            sessions = connection.execute(
                f"""SELECT child_id, status, check_in_at, check_out_at, pickup_person_name, updated_at
                    FROM attendance_sessions WHERE local_date = ? AND child_id IN ({placeholders})""",
                (local_date, *child_ids),
            ).fetchall()
            legacy_rows = connection.execute(
                f"""SELECT child_id, status, check_in, updated_at FROM child_attendance
                    WHERE child_id IN ({placeholders})""",
                tuple(child_ids),
            ).fetchall()
        records: dict[str, dict[str, Any]] = {}
        for row in legacy_rows:
            try:
                updated_at = datetime.fromisoformat(row["updated_at"])
                if updated_at.astimezone(LOCAL_ZONE).date().isoformat() != local_date:
                    continue
            except (TypeError, ValueError):
                continue
            records[row["child_id"]] = {
                "child_id": row["child_id"], "status": row["status"],
                "check_in": row["check_in"] or "Belum dicatat", "check_out": "Belum dicatat",
                "pickup_person_name": None, "updated_at": row["updated_at"],
            }
        for row in sessions:
            records[row["child_id"]] = {
                "child_id": row["child_id"], "status": row["status"],
                "check_in": self._time_label(row["check_in_at"]),
                "check_out": self._time_label(row["check_out_at"]),
                "pickup_person_name": row["pickup_person_name"] if role != "doctor" else None,
                "updated_at": row["updated_at"],
            }
        return sorted(records.values(), key=lambda item: (item["updated_at"], item["child_id"]), reverse=True)

    def list_events(self, child_ids: list[str]) -> list[dict[str, Any]]:
        if not child_ids:
            return []
        placeholders = ",".join("?" for _ in child_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT events.id, events.child_id, events.local_date, events.event_type,
                          events.status, actor.name AS actor_name, events.pickup_person_name,
                          events.parent_confirmation_method, events.pickup_name_match_confirmed,
                          events.occurred_at
                   FROM attendance_events AS events
                   LEFT JOIN auth_users AS actor ON actor.id = events.actor_user_id
                   WHERE events.child_id IN ({placeholders})
                   ORDER BY events.occurred_at DESC, events.rowid DESC LIMIT 250""",
                tuple(child_ids),
            ).fetchall()
        return [
            {**dict(row), "pickup_name_match_confirmed": bool(row["pickup_name_match_confirmed"])}
            for row in rows
        ]
