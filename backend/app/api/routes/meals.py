from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.dependencies import require_roles
from app.models.schemas import MealCatalogCreate


router = APIRouter(prefix="/meals", tags=["Menu dan gizi"])


@router.get("/catalog")
def list_meal_catalog(
    request: Request,
    user: dict = Depends(require_roles("caregiver", "doctor", "admin", "parent")),
) -> dict:
    return {"meals": request.app.state.meal_repository.list_active(user.get("organization_ids", []))}


@router.post("/catalog", status_code=201)
def create_meal(
    payload: MealCatalogCreate,
    request: Request,
    organization_id: str | None = Query(default=None, min_length=1, max_length=80),
    user: dict = Depends(require_roles("doctor", "admin")),
) -> dict:
    organization_ids = user.get("organization_ids", [])
    if organization_id is None:
        if len(organization_ids) != 1:
            raise HTTPException(status_code=422, detail="Pilih daycare pemilik katalog menu.")
        organization_id = organization_ids[0]
    if organization_id not in organization_ids:
        raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke daycare tersebut.")
    meal = request.app.state.meal_repository.create(payload.model_dump(), user["id"], organization_id)
    return {"meal": meal}
