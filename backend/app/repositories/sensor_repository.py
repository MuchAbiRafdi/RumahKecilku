from __future__ import annotations

import hmac
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class SensorRepository:
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
                CREATE TABLE IF NOT EXISTS sensor_devices (
                    device_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    room_id TEXT NOT NULL,
                    secret_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','revoked')),
                    created_at TEXT NOT NULL,
                    revoked_at TEXT,
                    FOREIGN KEY(organization_id) REFERENCES daycare_organizations(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sensor_devices_org_status ON sensor_devices(organization_id, status)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    organization_id TEXT,
                    room_id TEXT NOT NULL,
                    temperature_c REAL NOT NULL,
                    humidity_pct REAL NOT NULL,
                    measured_at TEXT NOT NULL,
                    received_at TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(sensor_readings)")}
            if "organization_id" not in columns:
                connection.execute("ALTER TABLE sensor_readings ADD COLUMN organization_id TEXT")
            # Historical readings without an organization are intentionally not exposed;
            # the former global device key cannot establish their tenant reliably.
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sensor_readings_org_room_measured ON sensor_readings(organization_id, room_id, measured_at DESC)"
            )

    def register_device(
        self,
        *,
        organization_id: str,
        device_id: str,
        room_id: str,
        secret_hash: str,
    ) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO sensor_devices
                   (device_id, organization_id, room_id, secret_hash, status, created_at)
                   VALUES (?, ?, ?, ?, 'active', ?)""",
                (device_id, organization_id, room_id, secret_hash, created_at),
            )
        return {
            "device_id": device_id,
            "organization_id": organization_id,
            "room_id": room_id,
            "status": "active",
            "created_at": created_at,
        }

    def device_exists(self, device_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM sensor_devices WHERE device_id = ? LIMIT 1",
                (device_id,),
            ).fetchone()
        return row is not None

    def authorize_device(self, *, device_id: str, room_id: str, secret_hash: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT device.secret_hash, device.organization_id
                   FROM sensor_devices AS device
                   JOIN daycare_organizations AS organization ON organization.id = device.organization_id
                   WHERE device.device_id = ? AND device.room_id = ? AND device.status = 'active'
                     AND organization.status = 'active'""",
                (device_id, room_id),
            ).fetchone()
        if row is None or not hmac.compare_digest(row["secret_hash"], secret_hash):
            return None
        return row["organization_id"]

    def active_device_ids(self, organization_ids: list[str]) -> list[str]:
        if not organization_ids:
            return []
        placeholders = ",".join("?" for _ in organization_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT device_id FROM sensor_devices WHERE status = 'active' AND organization_id IN ({placeholders}) ORDER BY device_id",
                tuple(organization_ids),
            ).fetchall()
        return [row["device_id"] for row in rows]

    def record(
        self,
        *,
        device_id: str,
        organization_id: str,
        room_id: str,
        temperature_c: float,
        humidity_pct: float,
        measured_at: datetime,
    ) -> dict[str, Any]:
        normalized_time = measured_at.astimezone(timezone.utc).isoformat(timespec="seconds")
        received_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = {
            "id": f"reading-{uuid4().hex[:12]}",
            "device_id": device_id,
            "organization_id": organization_id,
            "room_id": room_id,
            "temperature_c": float(temperature_c),
            "humidity_pct": float(humidity_pct),
            "measured_at": normalized_time,
            "received_at": received_at,
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO sensor_readings
                   (id, device_id, organization_id, room_id, temperature_c, humidity_pct, measured_at, received_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["id"], record["device_id"], record["organization_id"], record["room_id"],
                    record["temperature_c"], record["humidity_pct"], record["measured_at"], record["received_at"],
                ),
            )
        return record

    def summary(
        self,
        organization_ids: list[str],
        room_id: str | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        organization_ids = list(dict.fromkeys(organization_ids))
        if not organization_ids:
            return {"connected": False, "fresh": False, "latest": None, "readings": []}
        device_ids = self.active_device_ids(organization_ids)
        if not device_ids:
            return {"connected": False, "fresh": False, "latest": None, "readings": []}
        org_placeholders = ",".join("?" for _ in organization_ids)
        device_placeholders = ",".join("?" for _ in device_ids)
        where = f"organization_id IN ({org_placeholders}) AND device_id IN ({device_placeholders})"
        parameters: list[Any] = [*organization_ids, *device_ids]
        if room_id:
            where += " AND room_id = ?"
            parameters.append(room_id)
        with self._connect() as connection:
            latest = connection.execute(
                f"SELECT * FROM sensor_readings WHERE {where} ORDER BY measured_at DESC, received_at DESC LIMIT 1",
                tuple(parameters),
            ).fetchone()
            if latest is None:
                rows = []
            else:
                row_where = where
                row_parameters = list(parameters)
                if not room_id:
                    row_where += " AND room_id = ?"
                    row_parameters.append(latest["room_id"])
                rows = connection.execute(
                    f"SELECT * FROM sensor_readings WHERE {row_where} ORDER BY measured_at DESC, received_at DESC LIMIT ?",
                    (*row_parameters, limit),
                ).fetchall()
        if latest is None:
            return {"connected": False, "fresh": False, "latest": None, "readings": []}
        measured_at = datetime.fromisoformat(latest["measured_at"])
        now = datetime.now(timezone.utc)
        fresh = measured_at >= now - timedelta(minutes=15) and measured_at <= now + timedelta(minutes=5)
        return {
            "connected": True,
            "fresh": fresh,
            "latest": {
                "id": latest["id"],
                "device_id": latest["device_id"],
                "room_id": latest["room_id"],
                "temperature_c": latest["temperature_c"],
                "humidity_pct": latest["humidity_pct"],
                "measured_at": latest["measured_at"],
                "received_at": latest["received_at"],
            },
            "readings": [
                {
                    "id": row["id"],
                    "device_id": row["device_id"],
                    "room_id": row["room_id"],
                    "temperature_c": row["temperature_c"],
                    "humidity_pct": row["humidity_pct"],
                    "measured_at": row["measured_at"],
                }
                for row in reversed(rows)
            ],
        }
