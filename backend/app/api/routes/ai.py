from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import require_roles
from app.ai.messacare import create_activity_announcement
from app.models.schemas import MessaCareAnnouncementRequest

router = APIRouter(prefix="/ai", tags=["AI demo"])


@router.post("/messacare/announcement")
def generate_messacare_announcement(
    payload: MessaCareAnnouncementRequest,
    _user: dict = Depends(require_roles("caregiver")),
) -> dict:
    return create_activity_announcement(payload)
