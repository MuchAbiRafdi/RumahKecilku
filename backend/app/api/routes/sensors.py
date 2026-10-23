from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.dependencies import require_roles
from app.models.schemas import SensorDeviceRegister, SensorReadingCreate


router = APIRouter(prefix="/sensors", tags=["Sensor ruang"])


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@router.get("/summary")
def sensor_summary(
    request: Request,
    room_id: str | None = Query(default=None, min_length=1, max_length=80),
    limit: int = Query(default=12, ge=1, le=50),
    user: dict = Depends(require_roles("caregiver", "doctor", "admin")),
) -> dict:
    return request.app.state.sensor_repository.summary(
        organization_ids=user.get("organization_ids", []),
        room_id=room_id,
        limit=limit,
    )


@router.post("/devices", status_code=status.HTTP_201_CREATED)
def register_sensor_device(
    payload: SensorDeviceRegister,
    request: Request,
    organization_id: str | None = Query(default=None, min_length=1, max_length=80),
    user: dict = Depends(require_roles("admin")),
) -> dict:
    organization_ids = user.get("organization_ids", [])
    if organization_id is None:
        if len(organization_ids) != 1:
            raise HTTPException(status_code=422, detail="Pilih daycare pemilik perangkat sensor.")
        organization_id = organization_ids[0]
    if organization_id not in organization_ids:
        raise HTTPException(status_code=403, detail="Akun admin ini tidak memiliki akses ke daycare tersebut.")

    secret = secrets.token_urlsafe(32)
    try:
        device = request.app.state.sensor_repository.register_device(
            organization_id=organization_id,
            device_id=payload.device_id,
            room_id=payload.room_id,
            secret_hash=_digest(secret),
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="ID perangkat sudah terdaftar. Gunakan ID unik untuk perangkat ini.") from exc
    # The raw key is returned once and never stored; configure the device securely.
    return {"device": device, "sensor_key": secret}


@router.post("/readings", status_code=status.HTTP_201_CREATED)
def receive_sensor_reading(
    payload: SensorReadingCreate,
    request: Request,
    sensor_key: str | None = Header(default=None, alias="X-Sensor-Key"),
) -> dict:
    repository = request.app.state.sensor_repository
    if not repository.device_exists(payload.device_id):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Perangkat sensor belum didaftarkan oleh admin daycare.",
        )
    if not sensor_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kunci sensor tidak valid.")
    organization_id = repository.authorize_device(
        device_id=payload.device_id,
        room_id=payload.room_id,
        secret_hash=_digest(sensor_key),
    )
    if organization_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kunci atau ruang perangkat tidak valid.")

    now = datetime.now(timezone.utc)
    measured_at = payload.measured_at.astimezone(timezone.utc) if payload.measured_at else now
    if measured_at > now + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Waktu pembacaan sensor tidak boleh jauh di masa mendatang.")
    if measured_at < now - timedelta(days=7):
        raise HTTPException(status_code=422, detail="Pembacaan sensor lebih lama dari jendela penyimpanan 7 hari.")

    reading = repository.record(
        device_id=payload.device_id,
        organization_id=organization_id,
        room_id=payload.room_id,
        temperature_c=payload.temperature_c,
        humidity_pct=payload.humidity_pct,
        measured_at=measured_at,
    )
    return {"reading": reading}
