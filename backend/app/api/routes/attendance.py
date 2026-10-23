from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.dependencies import require_roles
from app.models.schemas import AttendanceCheckInCreate, AttendanceCheckOutCreate, AttendanceUpdate, PickupAuthorizationCreate


router = APIRouter(prefix="/attendance", tags=["Kehadiran"])


def _repository(request: Request):
    return request.app.state.attendance_repository


def _authorized_child_organization(request: Request, user: dict, child_id: str) -> str:
    if child_id not in user.get("child_ids", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun ini tidak memiliki akses ke profil anak tersebut.",
        )
    organization_id = request.app.state.auth_repository.get_organization_id_for_child(child_id)
    if organization_id is None or organization_id not in user.get("organization_ids", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Profil anak tidak berada pada daycare aktif akun ini.",
        )
    return organization_id


@router.get("")
def list_attendance(
    request: Request,
    user: dict = Depends(require_roles("caregiver", "doctor", "admin", "parent")),
) -> dict:
    return {"attendance": _repository(request).list_for_user(user["role"], user.get("child_ids", []))}


@router.post("")
def update_attendance(
    payload: AttendanceUpdate,
    request: Request,
    user: dict = Depends(require_roles("caregiver", "admin")),
) -> dict:
    _authorized_child_organization(request, user, payload.child_id)
    try:
        attendance = _repository(request).update(payload.child_id, payload.status, user["id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"attendance": attendance}


@router.get("/children/{child_id}/authorized-pickups")
def list_authorized_pickups(
    child_id: str,
    request: Request,
    user: dict = Depends(require_roles("caregiver", "admin")),
) -> dict:
    organization_id = _authorized_child_organization(request, user, child_id)
    pickups = _repository(request).list_authorized_pickups(organization_id=organization_id, child_id=child_id)
    if user["role"] == "caregiver":
        pickups = [
            {key: pickup[key] for key in ("id", "child_id", "name", "relationship", "status")}
            for pickup in pickups
        ]
    return {"authorized_pickups": pickups}


@router.post("/children/{child_id}/authorized-pickups", status_code=201)
def create_authorized_pickup(
    child_id: str,
    payload: PickupAuthorizationCreate,
    request: Request,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    organization_id = _authorized_child_organization(request, user, child_id)
    try:
        pickup = _repository(request).create_authorized_pickup(
            organization_id=organization_id,
            child_id=child_id,
            name=payload.name,
            relationship=payload.relationship,
            parent_confirmation_method=payload.parent_confirmation_method,
            admin_user_id=user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"authorized_pickup": pickup}


@router.post("/children/{child_id}/authorized-pickups/{pickup_id}/revoke")
def revoke_authorized_pickup(
    child_id: str,
    pickup_id: str,
    request: Request,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    organization_id = _authorized_child_organization(request, user, child_id)
    pickup = _repository(request).revoke_authorized_pickup(
        organization_id=organization_id,
        child_id=child_id,
        pickup_id=pickup_id,
        admin_user_id=user["id"],
    )
    if pickup is None:
        raise HTTPException(status_code=404, detail="Penjemput aktif untuk profil ini tidak ditemukan.")
    return {"authorized_pickup": pickup}


@router.post("/check-in")
def check_in(
    payload: AttendanceCheckInCreate,
    request: Request,
    user: dict = Depends(require_roles("caregiver", "admin")),
) -> dict:
    organization_id = _authorized_child_organization(request, user, payload.child_id)
    try:
        attendance = _repository(request).check_in(
            organization_id=organization_id, child_id=payload.child_id, actor_user_id=user["id"]
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"attendance": attendance}


@router.post("/check-out")
def check_out(
    payload: AttendanceCheckOutCreate,
    request: Request,
    user: dict = Depends(require_roles("caregiver", "admin")),
) -> dict:
    organization_id = _authorized_child_organization(request, user, payload.child_id)
    try:
        attendance = _repository(request).check_out(
            organization_id=organization_id,
            child_id=payload.child_id,
            pickup_authorization_id=payload.pickup_authorization_id,
            actor_user_id=user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"attendance": attendance}


@router.get("/events")
def list_attendance_events(
    request: Request,
    child_id: str | None = Query(default=None, min_length=1, max_length=80),
    user: dict = Depends(require_roles("admin")),
) -> dict:
    child_ids = user.get("child_ids", [])
    if child_id is not None:
        _authorized_child_organization(request, user, child_id)
        child_ids = [child_id]
    return {"events": _repository(request).list_events(child_ids)}
