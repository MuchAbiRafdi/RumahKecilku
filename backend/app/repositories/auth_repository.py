from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.security import hash_password, verify_password


DEMO_ACCOUNTS = (
    {"name": "Rani · Pengasuh demo", "email": "pengasuh@rumahkecilku.demo", "role": "caregiver"},
    {"name": "dr. Dita · Dokter demo", "email": "dokter@rumahkecilku.demo", "role": "doctor"},
    {"name": "Admin operasional · demo", "email": "admin@rumahkecilku.demo", "role": "admin"},
    {"name": "Keluarga Irfan · demo", "email": "orangtua@rumahkecilku.demo", "role": "parent"},
)
DEMO_ORGANIZATION = {
    "id": "org-demo-rumah-kecilku",
    "name": "Rumah Kecilku · Daycare Contoh",
    "slug": "rumah-kecilku-demo",
}
DEMO_PASSWORD = "RK-Preview-2026!"


class AuthRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _migrate_admin_role_constraint(connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'auth_users'"
        ).fetchone()
        if row is None or "'admin'" in (row["sql"] or ""):
            return

        # SQLite cannot alter a CHECK constraint in-place. Rebuild only this small identity
        # table transactionally; preserve all account IDs, hashes, roles, and timestamps.
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE auth_users_admin_migration (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                role TEXT NOT NULL CHECK(role IN ('parent','caregiver','doctor','admin')),
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO auth_users_admin_migration (id, name, email, role, password_hash, created_at)
                SELECT id, name, email, role, password_hash, created_at FROM auth_users;
            DROP TABLE auth_users;
            ALTER TABLE auth_users_admin_migration RENAME TO auth_users;
            COMMIT;
            """
        )
        connection.execute("PRAGMA foreign_keys = ON")

    def initialize(self, include_demo_accounts: bool = False) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    role TEXT NOT NULL CHECK(role IN ('parent','caregiver','doctor','admin')),
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._migrate_admin_role_constraint(connection)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_login_attempts (
                    identity_hash TEXT PRIMARY KEY,
                    window_started_at TEXT NOT NULL,
                    failure_count INTEGER NOT NULL CHECK(failure_count >= 0)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_user_children (
                    user_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    relationship TEXT NOT NULL DEFAULT 'wali',
                    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'verified', 'rejected', 'revoked')),
                    verification_method TEXT,
                    institution_verified_at TEXT,
                    institution_verified_by TEXT,
                    parent_confirmed_at TEXT,
                    parent_decided_at TEXT,
                    revoked_at TEXT,
                    revoked_by TEXT,
                    PRIMARY KEY (user_id, child_id),
                    FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE
                )
                """
            )
            guardian_link_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(auth_user_children)")
            }
            guardian_link_migrations = (
                ("relationship", "TEXT NOT NULL DEFAULT 'wali'"),
                ("status", "TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'verified', 'rejected', 'revoked'))"),
                ("verification_method", "TEXT"),
                ("institution_verified_at", "TEXT"),
                ("institution_verified_by", "TEXT"),
                ("parent_confirmed_at", "TEXT"),
                ("parent_decided_at", "TEXT"),
                ("revoked_at", "TEXT"),
                ("revoked_by", "TEXT"),
            )
            for column, definition in guardian_link_migrations:
                if column not in guardian_link_columns:
                    connection.execute(f"ALTER TABLE auth_user_children ADD COLUMN {column} {definition}")

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS child_guardian_link_audit (
                    id TEXT PRIMARY KEY,
                    child_id TEXT NOT NULL,
                    parent_user_id TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL,
                    action TEXT NOT NULL CHECK(action IN ('requested', 'confirmed', 'rejected', 'revoked', 'reissued')),
                    relationship TEXT NOT NULL,
                    verification_method TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_guardian_audit_child_created ON child_guardian_link_audit(child_id, created_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS child_profile_audit (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL,
                    action TEXT NOT NULL CHECK(action = 'updated'),
                    changed_fields TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_child_profile_audit_child_created ON child_profile_audit(child_id, created_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daycare_organizations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suspended')),
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS organization_memberships (
                    organization_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('parent','caregiver','doctor','admin')),
                    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('invited','active','suspended','revoked')),
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (organization_id, user_id),
                    FOREIGN KEY(organization_id) REFERENCES daycare_organizations(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_org_memberships_user_status ON organization_memberships(user_id, status)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS child_profiles (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    birth_date TEXT,
                    room TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(organization_id) REFERENCES daycare_organizations(id) ON DELETE RESTRICT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_child_profiles_org_status ON child_profiles(organization_id, status, name COLLATE NOCASE)"
            )
            if include_demo_accounts:
                existing = {
                    row["email"].lower(): row
                    for row in connection.execute("SELECT id, name, email, role, password_hash FROM auth_users")
                }
                created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                for account in DEMO_ACCOUNTS:
                    current = existing.get(account["email"])
                    if current is None:
                        demo_user_id = f"demo-{account['role']}"
                        connection.execute("DELETE FROM auth_sessions WHERE user_id = ?", (demo_user_id,))
                        connection.execute(
                            "INSERT INTO auth_users (id, name, email, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                demo_user_id,
                                account["name"],
                                account["email"],
                                account["role"],
                                hash_password(DEMO_PASSWORD),
                                created_at,
                            ),
                        )
                    elif current["role"] != account["role"] or not verify_password(DEMO_PASSWORD, current["password_hash"]):
                        # Reserved demo identities are rotated only in explicitly enabled preview mode.
                        connection.execute(
                            "UPDATE auth_users SET name = ?, role = ?, password_hash = ? WHERE email = ? COLLATE NOCASE",
                            (account["name"], account["role"], hash_password(DEMO_PASSWORD), account["email"]),
                        )
                        # A credential/role reset invalidates sessions issued under the old account state.
                        connection.execute("DELETE FROM auth_sessions WHERE user_id = ?", (current["id"],))
                demo_parent = connection.execute(
                    "SELECT id FROM auth_users WHERE email = ? COLLATE NOCASE AND role = 'parent'",
                    ("orangtua@rumahkecilku.demo",),
                ).fetchone()
                connection.execute(
                    "INSERT OR IGNORE INTO daycare_organizations (id, name, slug, created_at) VALUES (?, ?, ?, ?)",
                    (DEMO_ORGANIZATION["id"], DEMO_ORGANIZATION["name"], DEMO_ORGANIZATION["slug"], created_at),
                )
                for account in DEMO_ACCOUNTS:
                    demo_user = connection.execute(
                        "SELECT id, role FROM auth_users WHERE email = ? COLLATE NOCASE",
                        (account["email"],),
                    ).fetchone()
                    if demo_user is None:
                        continue
                    connection.execute(
                        """INSERT INTO organization_memberships (organization_id, user_id, role, status, joined_at)
                           VALUES (?, ?, ?, 'active', ?)
                           ON CONFLICT(organization_id, user_id) DO UPDATE SET role = excluded.role, status = 'active'""",
                        (DEMO_ORGANIZATION["id"], demo_user["id"], demo_user["role"], created_at),
                    )

                # Synthetic preview roster: one profile for every official KPSP age band (3–72 months).
                # These names and dates are fictional and must never be treated as real child data.
                demo_children = (
                    ("a", "Irfan", "2024-10-23", "Ruang Melati"),
                    ("b", "Rian", "2025-10-23", "Ruang Kenanga"),
                    ("c", "Raka", "2023-10-23", "Ruang Melati"),
                    ("d", "Siti", "2022-10-23", "Ruang Anggrek"),
                    ("e", "Alya", "2026-07-23", "Ruang Kenanga"),
                    ("f", "Bima", "2026-04-23", "Ruang Melati"),
                    ("g", "Citra", "2026-01-23", "Ruang Kenanga"),
                    ("h", "Dafa", "2025-07-23", "Ruang Anggrek"),
                    ("i", "Elsa", "2025-04-23", "Ruang Melati"),
                    ("j", "Fajar", "2025-01-23", "Ruang Kenanga"),
                    ("k", "Gita", "2024-04-23", "Ruang Anggrek"),
                    ("l", "Hana", "2023-04-23", "Ruang Melati"),
                    ("m", "Intan", "2022-04-23", "Ruang Kenanga"),
                    ("n", "Jovan", "2021-10-23", "Ruang Anggrek"),
                    ("o", "Kirana", "2021-04-23", "Ruang Melati"),
                    ("p", "Lala", "2020-10-23", "Ruang Kenanga"),
                )
                for child_id, child_name, birth_date, room in demo_children:
                    connection.execute(
                        """INSERT INTO child_profiles
                           (id, organization_id, name, birth_date, room, status, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                           ON CONFLICT(id) DO UPDATE SET
                               organization_id = excluded.organization_id,
                               name = excluded.name,
                               birth_date = excluded.birth_date,
                               room = excluded.room,
                               status = 'active',
                               updated_at = excluded.updated_at""",
                        (child_id, DEMO_ORGANIZATION["id"], child_name, birth_date, room, created_at, created_at),
                    )

                if demo_parent:
                    connection.execute(
                        """INSERT INTO auth_user_children (
                               user_id, child_id, created_at, relationship, status,
                               verification_method, institution_verified_at, parent_confirmed_at
                           ) VALUES (?, ?, ?, 'Wali demo', 'verified', 'synthetic_demo_seed', ?, ?)
                           ON CONFLICT(user_id, child_id) DO UPDATE SET
                               relationship = 'Wali demo', status = 'verified',
                               verification_method = 'synthetic_demo_seed',
                               institution_verified_at = COALESCE(auth_user_children.institution_verified_at, excluded.institution_verified_at),
                               parent_confirmed_at = COALESCE(auth_user_children.parent_confirmed_at, excluded.parent_confirmed_at),
                               revoked_at = NULL, revoked_by = NULL
                           WHERE auth_user_children.status = 'pending'
                             AND auth_user_children.institution_verified_at IS NULL""",
                        (demo_parent["id"], "a", created_at, created_at, created_at),
                    )

    @staticmethod
    def _public_user(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"]}

    def _with_access_scope(self, user: dict[str, Any] | None) -> dict[str, Any] | None:
        if user is None:
            return None
        return {
            **user,
            "organization_ids": self.get_organization_ids(user["id"]),
            "child_ids": self.get_accessible_child_ids(user["id"], user["role"]),
        }

    def get_organization_ids(self, user_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT membership.organization_id
                   FROM organization_memberships AS membership
                   JOIN daycare_organizations AS organization ON organization.id = membership.organization_id
                   WHERE membership.user_id = ? AND membership.status = 'active' AND organization.status = 'active'
                   ORDER BY membership.organization_id""",
                (user_id,),
            ).fetchall()
        return [row["organization_id"] for row in rows]

    def get_accessible_child_ids(self, user_id: str, role: str) -> list[str]:
        with self._connect() as connection:
            if role == "parent":
                rows = connection.execute(
                    """SELECT DISTINCT profile.id
                       FROM auth_user_children AS link
                       JOIN child_profiles AS profile ON profile.id = link.child_id
                       JOIN daycare_organizations AS organization ON organization.id = profile.organization_id
                       JOIN organization_memberships AS membership
                         ON membership.organization_id = profile.organization_id AND membership.user_id = link.user_id
                       WHERE link.user_id = ? AND link.status = 'verified'
                         AND membership.role = 'parent' AND membership.status = 'active'
                         AND organization.status = 'active' AND profile.status = 'active'
                       ORDER BY profile.id""",
                    (user_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT DISTINCT profile.id
                       FROM child_profiles AS profile
                       JOIN daycare_organizations AS organization ON organization.id = profile.organization_id
                       JOIN organization_memberships AS membership ON membership.organization_id = profile.organization_id
                       WHERE membership.user_id = ? AND membership.role = ? AND membership.status = 'active'
                         AND organization.status = 'active' AND profile.status = 'active'
                       ORDER BY profile.id""",
                    (user_id, role),
                ).fetchall()
        return [row["id"] for row in rows]

    def can_access_child(self, user_id: str, role: str, child_id: str) -> bool:
        return child_id in self.get_accessible_child_ids(user_id, role)

    def get_organization_id_for_child(self, child_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT organization_id FROM child_profiles WHERE id = ? AND status = 'active'",
                (child_id,),
            ).fetchone()
        return row["organization_id"] if row else None

    def list_child_profiles(self, user_id: str, role: str) -> list[dict[str, Any]]:
        child_ids = self.get_accessible_child_ids(user_id, role)
        if not child_ids:
            return []
        placeholders = ",".join("?" for _ in child_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT id, organization_id, name, birth_date, room, status, created_at, updated_at
                    FROM child_profiles WHERE status = 'active' AND id IN ({placeholders})
                    ORDER BY name COLLATE NOCASE, id""",
                tuple(child_ids),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_organization(self, name: str, slug: str, *, organization_id: str | None = None) -> dict[str, str]:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = {
            "id": organization_id or f"org-{uuid4().hex[:16]}",
            "name": " ".join(name.split()),
            "slug": slug.strip().lower(),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO daycare_organizations (id, name, slug, created_at) VALUES (?, ?, ?, ?)",
                (record["id"], record["name"], record["slug"], created_at),
            )
        return record

    def add_organization_member(self, organization_id: str, user_id: str, role: str, *, status: str = "active") -> None:
        joined_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            account = connection.execute(
                "SELECT role FROM auth_users WHERE id = ?",
                (user_id,),
            ).fetchone()
            organization = connection.execute(
                "SELECT 1 FROM daycare_organizations WHERE id = ? AND status = 'active'",
                (organization_id,),
            ).fetchone()
            if account is None or organization is None or account["role"] != role:
                raise ValueError("Membership harus sesuai dengan akun dan organisasi aktif.")
            connection.execute(
                """INSERT INTO organization_memberships (organization_id, user_id, role, status, joined_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(organization_id, user_id) DO UPDATE SET role = excluded.role, status = excluded.status""",
                (organization_id, user_id, role, status, joined_at),
            )

    def create_child_profile(
        self,
        organization_id: str,
        name: str,
        birth_date: str | None = None,
        room: str = "",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = {
            "id": f"child-{uuid4().hex[:16]}",
            "organization_id": organization_id,
            "name": " ".join(name.split()),
            "birth_date": birth_date,
            "room": " ".join(room.split()),
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO child_profiles
                   (id, organization_id, name, birth_date, room, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'active', ?, ?)""",
                (record["id"], organization_id, record["name"], birth_date, record["room"], now, now),
            )
        return record

    def update_child_profile(
        self,
        *,
        child_id: str,
        admin_user_id: str,
        organization_ids: list[str],
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        allowed_fields = {"name", "birth_date", "room"}
        if not updates or any(field not in allowed_fields for field in updates):
            raise ValueError("Kolom profil yang diperbarui tidak valid.")
        normalized = dict(updates)
        if "name" in normalized and normalized["name"] is not None:
            normalized["name"] = " ".join(str(normalized["name"]).split())
        if "room" in normalized and normalized["room"] is not None:
            normalized["room"] = " ".join(str(normalized["room"]).split())
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            child = self._active_admin_child_organization(connection, child_id, admin_user_id, organization_ids)
            if child is None:
                return None
            assignments = [f"{field} = ?" for field in normalized]
            values = list(normalized.values())
            assignments.append("updated_at = ?")
            values.extend([now, child_id])
            update = connection.execute(
                f"UPDATE child_profiles SET {', '.join(assignments)} WHERE id = ? AND status = 'active'",
                tuple(values),
            )
            if update.rowcount != 1:
                return None
            connection.execute(
                """INSERT INTO child_profile_audit
                   (id, organization_id, child_id, actor_user_id, action, changed_fields, created_at)
                   VALUES (?, ?, ?, ?, 'updated', ?, ?)""",
                (f"child-profile-audit-{uuid4().hex[:12]}", child["organization_id"], child_id, admin_user_id,
                 json.dumps(sorted(normalized), ensure_ascii=False), now),
            )
            row = connection.execute(
                """SELECT id, organization_id, name, birth_date, room, status, created_at, updated_at
                   FROM child_profiles WHERE id = ?""",
                (child_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_child_profile_audit(
        self, child_id: str, admin_user_id: str, organization_ids: list[str]
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if self._active_admin_child_organization(connection, child_id, admin_user_id, organization_ids) is None:
                return []
            rows = connection.execute(
                """SELECT audit.id, actor.name AS actor_name, audit.action,
                          audit.changed_fields, audit.created_at
                   FROM child_profile_audit AS audit
                   JOIN auth_users AS actor ON actor.id = audit.actor_user_id
                   WHERE audit.child_id = ? ORDER BY audit.created_at DESC, audit.rowid DESC LIMIT 100""",
                (child_id,),
            ).fetchall()
        return [
            {"id": row["id"], "actor_name": row["actor_name"], "action": row["action"],
             "changed_fields": json.loads(row["changed_fields"]), "created_at": row["created_at"]}
            for row in rows
        ]

    @staticmethod
    def _masked_email(email: str) -> str:
        local, separator, domain = email.partition("@")
        if not separator:
            return "alamat akun tersembunyi"
        return f"{local[:1]}***@{domain}"

    def _active_admin_child_organization(
        self,
        connection: sqlite3.Connection,
        child_id: str,
        admin_user_id: str,
        organization_ids: list[str],
    ) -> sqlite3.Row | None:
        if not organization_ids:
            return None
        placeholders = ",".join("?" for _ in organization_ids)
        return connection.execute(
            f"""SELECT profile.organization_id
                FROM child_profiles AS profile
                JOIN daycare_organizations AS organization
                  ON organization.id = profile.organization_id AND organization.status = 'active'
                JOIN organization_memberships AS membership
                  ON membership.organization_id = profile.organization_id
                 AND membership.user_id = ? AND membership.role = 'admin' AND membership.status = 'active'
                WHERE profile.id = ? AND profile.status = 'active'
                  AND profile.organization_id IN ({placeholders})""",
            (admin_user_id, child_id, *organization_ids),
        ).fetchone()

    def list_guardian_candidates(
        self, child_id: str, admin_user_id: str, organization_ids: list[str]
    ) -> list[dict[str, str]]:
        with self._connect() as connection:
            child = self._active_admin_child_organization(connection, child_id, admin_user_id, organization_ids)
            if child is None:
                return []
            rows = connection.execute(
                """SELECT users.id, users.name, users.email
                   FROM auth_users AS users
                   JOIN organization_memberships AS membership ON membership.user_id = users.id
                   WHERE users.role = 'parent' AND membership.role = 'parent'
                     AND membership.organization_id = ? AND membership.status = 'active'
                     AND NOT EXISTS (
                         SELECT 1 FROM auth_user_children AS link
                         WHERE link.user_id = users.id AND link.child_id = ?
                           AND (link.status = 'verified' OR (link.status = 'pending' AND link.institution_verified_at IS NOT NULL))
                     )
                   ORDER BY users.name COLLATE NOCASE, users.id""",
                (child["organization_id"], child_id),
            ).fetchall()
        return [
            {"id": row["id"], "name": row["name"], "email_hint": self._masked_email(row["email"])}
            for row in rows
        ]

    def list_guardian_links(
        self, child_id: str, admin_user_id: str, organization_ids: list[str]
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            child = self._active_admin_child_organization(connection, child_id, admin_user_id, organization_ids)
            if child is None:
                return []
            rows = connection.execute(
                """SELECT links.user_id, users.name, users.email, links.relationship, links.status,
                          links.verification_method, links.institution_verified_at,
                          links.institution_verified_by, links.parent_confirmed_at,
                          links.parent_decided_at, links.revoked_at, links.revoked_by
                   FROM auth_user_children AS links
                   JOIN auth_users AS users ON users.id = links.user_id AND users.role = 'parent'
                   WHERE links.child_id = ?
                   ORDER BY CASE links.status WHEN 'pending' THEN 0 WHEN 'verified' THEN 1 ELSE 2 END,
                            users.name COLLATE NOCASE, users.id""",
                (child_id,),
            ).fetchall()
        return [
            {
                "parent_user_id": row["user_id"],
                "name": row["name"],
                "email_hint": self._masked_email(row["email"]),
                "relationship": row["relationship"],
                "status": row["status"],
                "verification_method": row["verification_method"],
                "institution_verified_at": row["institution_verified_at"],
                "institution_verified_by": row["institution_verified_by"],
                "parent_confirmed_at": row["parent_confirmed_at"],
                "parent_decided_at": row["parent_decided_at"],
                "revoked_at": row["revoked_at"],
                "revoked_by": row["revoked_by"],
            }
            for row in rows
        ]

    def create_guardian_invitation(
        self,
        *,
        child_id: str,
        parent_user_id: str,
        admin_user_id: str,
        organization_ids: list[str],
        relationship: str,
        verification_method: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        relationship = " ".join(relationship.split())
        with self._connect() as connection:
            child = self._active_admin_child_organization(connection, child_id, admin_user_id, organization_ids)
            if child is None:
                raise PermissionError("Akun admin tidak memiliki akses ke profil anak ini.")
            parent = connection.execute(
                """SELECT users.id FROM auth_users AS users
                   JOIN organization_memberships AS membership ON membership.user_id = users.id
                   WHERE users.id = ? AND users.role = 'parent' AND membership.role = 'parent'
                     AND membership.organization_id = ? AND membership.status = 'active'""",
                (parent_user_id, child["organization_id"]),
            ).fetchone()
            if parent is None:
                raise LookupError("Akun wali tidak aktif pada daycare yang sama.")
            existing = connection.execute(
                "SELECT status, institution_verified_at FROM auth_user_children WHERE user_id = ? AND child_id = ?",
                (parent_user_id, child_id),
            ).fetchone()
            if existing and (
                existing["status"] == "verified"
                or (existing["status"] == "pending" and existing["institution_verified_at"] is not None)
            ):
                raise FileExistsError("Tautan wali sudah menunggu konfirmasi atau aktif.")
            action = "reissued" if existing else "requested"
            connection.execute(
                """INSERT INTO auth_user_children (
                       user_id, child_id, created_at, relationship, status,
                       verification_method, institution_verified_at, institution_verified_by,
                       parent_confirmed_at, parent_decided_at, revoked_at, revoked_by
                   ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, NULL, NULL, NULL, NULL)
                   ON CONFLICT(user_id, child_id) DO UPDATE SET
                       created_at = excluded.created_at, relationship = excluded.relationship,
                       status = 'pending', verification_method = excluded.verification_method,
                       institution_verified_at = excluded.institution_verified_at,
                       institution_verified_by = excluded.institution_verified_by,
                       parent_confirmed_at = NULL, parent_decided_at = NULL,
                       revoked_at = NULL, revoked_by = NULL""",
                (
                    parent_user_id, child_id, now, relationship, verification_method,
                    now, admin_user_id,
                ),
            )
            connection.execute(
                """INSERT INTO child_guardian_link_audit
                   (id, child_id, parent_user_id, actor_user_id, action, relationship, verification_method, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"guardian-audit-{uuid4().hex[:12]}", child_id, parent_user_id, admin_user_id,
                 action, relationship, verification_method, now),
            )
        return {
            "child_id": child_id,
            "parent_user_id": parent_user_id,
            "relationship": relationship,
            "status": "pending",
            "verification_method": verification_method,
            "institution_verified_at": now,
            "parent_confirmed_at": None,
        }

    def list_pending_guardian_invitations(self, parent_user_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT links.child_id, links.relationship, links.verification_method,
                          links.institution_verified_at, links.created_at,
                          profile.name AS child_name, organization.name AS organization_name,
                          admin.name AS verifier_name
                   FROM auth_user_children AS links
                   JOIN auth_users AS parent ON parent.id = links.user_id AND parent.role = 'parent'
                   JOIN child_profiles AS profile ON profile.id = links.child_id AND profile.status = 'active'
                   JOIN daycare_organizations AS organization
                     ON organization.id = profile.organization_id AND organization.status = 'active'
                   JOIN organization_memberships AS membership
                     ON membership.organization_id = profile.organization_id
                    AND membership.user_id = links.user_id AND membership.role = 'parent' AND membership.status = 'active'
                   LEFT JOIN auth_users AS admin ON admin.id = links.institution_verified_by
                   WHERE links.user_id = ? AND links.status = 'pending'
                     AND links.institution_verified_at IS NOT NULL
                   ORDER BY links.created_at DESC""",
                (parent_user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def decide_guardian_invitation(
        self, *, parent_user_id: str, child_id: str, accept: bool
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT links.relationship, links.verification_method, links.status
                   FROM auth_user_children AS links
                   JOIN auth_users AS parent ON parent.id = links.user_id AND parent.role = 'parent'
                   JOIN child_profiles AS profile ON profile.id = links.child_id AND profile.status = 'active'
                   JOIN daycare_organizations AS organization
                     ON organization.id = profile.organization_id AND organization.status = 'active'
                   JOIN organization_memberships AS membership
                     ON membership.organization_id = profile.organization_id
                    AND membership.user_id = links.user_id AND membership.role = 'parent' AND membership.status = 'active'
                   WHERE links.user_id = ? AND links.child_id = ?
                     AND links.status = 'pending' AND links.institution_verified_at IS NOT NULL""",
                (parent_user_id, child_id),
            ).fetchone()
            if row is None:
                return None
            status = "verified" if accept else "rejected"
            action = "confirmed" if accept else "rejected"
            connection.execute(
                """UPDATE auth_user_children SET status = ?, parent_confirmed_at = ?,
                          parent_decided_at = ?, revoked_at = NULL, revoked_by = NULL
                   WHERE user_id = ? AND child_id = ? AND status = 'pending'""",
                (status, now if accept else None, now, parent_user_id, child_id),
            )
            connection.execute(
                """INSERT INTO child_guardian_link_audit
                   (id, child_id, parent_user_id, actor_user_id, action, relationship, verification_method, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"guardian-audit-{uuid4().hex[:12]}", child_id, parent_user_id, parent_user_id,
                 action, row["relationship"], row["verification_method"], now),
            )
        return {
            "child_id": child_id,
            "parent_user_id": parent_user_id,
            "relationship": row["relationship"],
            "status": status,
            "parent_confirmed_at": now if accept else None,
            "parent_decided_at": now,
        }

    def revoke_guardian_link(
        self,
        *,
        child_id: str,
        parent_user_id: str,
        admin_user_id: str,
        organization_ids: list[str],
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            child = self._active_admin_child_organization(connection, child_id, admin_user_id, organization_ids)
            if child is None:
                raise PermissionError("Akun admin tidak memiliki akses ke profil anak ini.")
            row = connection.execute(
                "SELECT relationship, verification_method, status FROM auth_user_children WHERE user_id = ? AND child_id = ?",
                (parent_user_id, child_id),
            ).fetchone()
            if row is None or row["status"] not in {"pending", "verified"}:
                return None
            connection.execute(
                """UPDATE auth_user_children SET status = 'revoked', revoked_at = ?, revoked_by = ?,
                          parent_decided_at = ? WHERE user_id = ? AND child_id = ?""",
                (now, admin_user_id, now, parent_user_id, child_id),
            )
            connection.execute(
                """INSERT INTO child_guardian_link_audit
                   (id, child_id, parent_user_id, actor_user_id, action, relationship, verification_method, created_at)
                   VALUES (?, ?, ?, ?, 'revoked', ?, ?, ?)""",
                (f"guardian-audit-{uuid4().hex[:12]}", child_id, parent_user_id, admin_user_id,
                 row["relationship"], row["verification_method"], now),
            )
        return {"child_id": child_id, "parent_user_id": parent_user_id, "status": "revoked", "revoked_at": now}

    def list_guardian_link_audit(
        self, child_id: str, admin_user_id: str, organization_ids: list[str]
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            child = self._active_admin_child_organization(connection, child_id, admin_user_id, organization_ids)
            if child is None:
                return []
            rows = connection.execute(
                """SELECT audit.parent_user_id, parent.name AS parent_name,
                          actor.name AS actor_name, audit.action, audit.relationship,
                          audit.verification_method, audit.created_at
                   FROM child_guardian_link_audit AS audit
                   JOIN auth_users AS parent ON parent.id = audit.parent_user_id
                   JOIN auth_users AS actor ON actor.id = audit.actor_user_id
                   WHERE audit.child_id = ? ORDER BY audit.created_at DESC, audit.rowid DESC LIMIT 100""",
                (child_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_child_ids(self, user_id: str) -> list[str]:
        with self._connect() as connection:
            row = connection.execute("SELECT role FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        return self.get_accessible_child_ids(user_id, row["role"]) if row else []

    def has_linked_parent(self, child_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT 1
                   FROM auth_user_children AS links
                   JOIN organization_memberships AS membership
                     ON membership.user_id = links.user_id AND membership.role = 'parent' AND membership.status = 'active'
                   JOIN child_profiles AS profile
                     ON profile.id = links.child_id AND profile.organization_id = membership.organization_id
                   JOIN daycare_organizations AS organization
                     ON organization.id = profile.organization_id AND organization.status = 'active'
                   WHERE links.child_id = ? AND links.status = 'verified' LIMIT 1""",
                (child_id,),
            ).fetchone()
        return row is not None

    def get_parent_user_ids(self, child_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT users.id FROM auth_user_children AS links
                   JOIN auth_users AS users ON users.id = links.user_id AND users.role = 'parent'
                   JOIN organization_memberships AS membership
                     ON membership.user_id = users.id AND membership.role = 'parent' AND membership.status = 'active'
                   JOIN child_profiles AS profile
                     ON profile.id = links.child_id AND profile.organization_id = membership.organization_id
                   JOIN daycare_organizations AS organization
                     ON organization.id = profile.organization_id AND organization.status = 'active'
                   WHERE links.child_id = ? AND links.status = 'verified' ORDER BY users.id""",
                (child_id,),
            ).fetchall()
        return [row["id"] for row in rows]

    def get_parent_user_ids_for_all_linked_children(self, organization_ids: list[str]) -> list[str]:
        if not organization_ids:
            return []
        placeholders = ",".join("?" for _ in organization_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT DISTINCT users.id FROM auth_user_children AS links
                   JOIN auth_users AS users ON users.id = links.user_id AND users.role = 'parent'
                   JOIN organization_memberships AS membership
                     ON membership.user_id = users.id AND membership.role = 'parent' AND membership.status = 'active'
                   JOIN child_profiles AS profile
                     ON profile.id = links.child_id AND profile.organization_id = membership.organization_id
                   WHERE profile.organization_id IN ({placeholders}) AND links.status = 'verified' ORDER BY users.id""",
                tuple(organization_ids),
            ).fetchall()
        return [row["id"] for row in rows]

    def get_user_ids_by_role(self, role: str, organization_ids: list[str] | None = None) -> list[str]:
        if not organization_ids:
            return []
        placeholders = ",".join("?" for _ in organization_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT DISTINCT users.id FROM auth_users AS users
                    JOIN organization_memberships AS membership ON membership.user_id = users.id
                    WHERE users.role = ? AND membership.role = ? AND membership.status = 'active'
                      AND membership.organization_id IN ({placeholders}) ORDER BY users.id""",
                (role, role, *organization_ids),
            ).fetchall()
        return [row["id"] for row in rows]

    def get_chat_contacts_for_child(self, requester_id: str, child_id: str) -> list[dict[str, str]]:
        with self._connect() as connection:
            requester = connection.execute(
                "SELECT id, role FROM auth_users WHERE id = ?", (requester_id,)
            ).fetchone()
            profile = connection.execute(
                """SELECT profile.organization_id FROM child_profiles AS profile
                   JOIN daycare_organizations AS organization ON organization.id = profile.organization_id
                   WHERE profile.id = ? AND profile.status = 'active' AND organization.status = 'active'""",
                (child_id,),
            ).fetchone()
            if requester is None or profile is None:
                return []
            organization_id = profile["organization_id"]

            if requester["role"] == "parent":
                owns_child = connection.execute(
                    """SELECT 1 FROM auth_user_children AS links
                       JOIN organization_memberships AS membership
                         ON membership.user_id = links.user_id AND membership.organization_id = ?
                       WHERE links.user_id = ? AND links.child_id = ? AND links.status = 'verified'
                         AND membership.role = 'parent' AND membership.status = 'active'""",
                    (organization_id, requester_id, child_id),
                ).fetchone()
                if owns_child is None:
                    return []
                rows = connection.execute(
                    """SELECT users.id, users.name, users.role FROM auth_users AS users
                       JOIN organization_memberships AS membership ON membership.user_id = users.id
                       WHERE membership.organization_id = ? AND membership.status = 'active'
                         AND membership.role IN ('caregiver', 'doctor') AND users.role = membership.role
                       ORDER BY membership.role, users.name""",
                    (organization_id,),
                ).fetchall()
            elif requester["role"] in {"caregiver", "doctor"}:
                requester_member = connection.execute(
                    """SELECT 1 FROM organization_memberships
                       WHERE organization_id = ? AND user_id = ? AND role = ? AND status = 'active'""",
                    (organization_id, requester_id, requester["role"]),
                ).fetchone()
                if requester_member is None:
                    return []
                parent_rows = connection.execute(
                    """SELECT DISTINCT users.id, users.name, users.role
                       FROM auth_user_children AS links
                       JOIN auth_users AS users ON users.id = links.user_id AND users.role = 'parent'
                       JOIN organization_memberships AS membership ON membership.user_id = users.id
                       WHERE links.child_id = ? AND links.status = 'verified' AND membership.organization_id = ?
                         AND membership.role = 'parent' AND membership.status = 'active'
                       ORDER BY users.name""",
                    (child_id, organization_id),
                ).fetchall()
                staff_rows = connection.execute(
                    """SELECT users.id, users.name, users.role FROM auth_users AS users
                       JOIN organization_memberships AS membership ON membership.user_id = users.id
                       WHERE membership.organization_id = ? AND membership.status = 'active'
                         AND membership.role = ? AND users.role = membership.role AND users.id != ?
                       ORDER BY users.name""",
                    (organization_id, 'doctor' if requester["role"] == "caregiver" else "caregiver", requester_id),
                ).fetchall()
                rows = [*parent_rows, *staff_rows]
            else:
                return []

        return [
            {"id": row["id"], "name": row["name"], "role": row["role"]}
            for row in rows
            if row["id"] != requester_id
        ]

    @staticmethod
    def hash_login_identifier(identifier: str) -> str:
        normalized = identifier.strip().casefold().encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    @staticmethod
    def is_demo_identity(user: dict[str, Any] | None) -> bool:
        if user is None:
            return False
        return user.get("email", "").casefold() in {account["email"].casefold() for account in DEMO_ACCOUNTS}

    def is_login_throttled(
        self,
        identity_hash: str,
        *,
        max_attempts: int = 10,
        window_seconds: int = 900,
    ) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).isoformat(timespec="seconds")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT failure_count, window_started_at FROM auth_login_attempts WHERE identity_hash = ?",
                (identity_hash,),
            ).fetchone()
        return bool(
            row
            and row["window_started_at"] > cutoff
            and row["failure_count"] >= max_attempts
        )

    def record_login_failure(self, identity_hash: str, *, window_seconds: int = 900) -> None:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat(timespec="seconds")
        cutoff = (now - timedelta(seconds=window_seconds)).isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_login_attempts WHERE window_started_at <= ?", (cutoff,))
            connection.execute(
                """
                INSERT INTO auth_login_attempts (identity_hash, window_started_at, failure_count)
                VALUES (?, ?, 1)
                ON CONFLICT(identity_hash) DO UPDATE SET
                    window_started_at = CASE
                        WHEN auth_login_attempts.window_started_at <= ? THEN excluded.window_started_at
                        ELSE auth_login_attempts.window_started_at
                    END,
                    failure_count = CASE
                        WHEN auth_login_attempts.window_started_at <= ? THEN 1
                        ELSE auth_login_attempts.failure_count + 1
                    END
                """,
                (identity_hash, now_text, cutoff, cutoff),
            )

    def clear_login_failures(self, identity_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_login_attempts WHERE identity_hash = ?", (identity_hash,))

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM auth_users WHERE email = ? COLLATE NOCASE",
                (email.strip().lower(),),
            ).fetchone()
        if row is None:
            return None
        user = self._with_access_scope(self._public_user(row))
        return {**user, "password_hash": row["password_hash"]}

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, email, role FROM auth_users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return self._with_access_scope(self._public_user(row))

    def create_user(self, name: str, email: str, role: str, password_hash: str) -> dict[str, Any]:
        user_id = f"usr-{uuid4().hex[:16]}"
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO auth_users (id, name, email, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, name.strip(), email.strip().lower(), role, password_hash, created_at),
            )
        return self._with_access_scope({
            "id": user_id,
            "name": name.strip(),
            "email": email.strip().lower(),
            "role": role,
        })

    def create_session(self, token_hash: str, user_id: str, expires_at: datetime) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token_hash, user_id, created_at, expires_at.astimezone(timezone.utc).isoformat(timespec="seconds")),
            )

    def get_user_for_session(self, token_hash: str) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.id, u.name, u.email, u.role
                FROM auth_sessions s JOIN auth_users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
        return self._with_access_scope(self._public_user(row))

    def delete_session(self, token_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))

    def prune_expired_sessions(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now,))
