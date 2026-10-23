from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import require_roles
from app.models.schemas import MilestoneObservationCreate


router = APIRouter(prefix="/observations", tags=["Pengamatan perkembangan"])


def _repository(request: Request):
    return request.app.state.observation_repository


@router.get("")
def list_observations(
    request: Request,
    user: dict = Depends(require_roles("caregiver", "doctor")),
) -> dict:
    return {"observations": _repository(request).list_for_user(user["role"], user.get("child_ids", []))}


@router.post("", status_code=201)
def create_observation(
    payload: MilestoneObservationCreate,
    request: Request,
    user: dict = Depends(require_roles("caregiver")),
) -> dict:
    if payload.child_id not in user.get("child_ids", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun ini tidak memiliki akses ke profil anak tersebut.",
        )
    record = _repository(request).create(payload.model_dump(), user["name"], user["id"])
    return {"observation": record}
