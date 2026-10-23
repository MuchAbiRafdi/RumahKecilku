from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import require_roles
from app.models.schemas import FamilyReminderCreate


router = APIRouter(prefix="/notifications", tags=["Pemberitahuan dan pengingat"])


def _repository(request: Request):
    return request.app.state.notification_repository



@router.get("")
def list_notifications(
    request: Request,
    user: dict = Depends(require_roles("caregiver", "doctor", "parent")),
) -> dict:
    return {
        "notifications": _repository(request).list_for_user(
            user_id=user["id"],
            role=user["role"],
            child_ids=user.get("child_ids", []),
            organization_ids=user.get("organization_ids", []),
        )
    }


@router.post("/reminders", status_code=status.HTTP_201_CREATED)
def create_reminder(
    payload: FamilyReminderCreate,
    request: Request,
    user: dict = Depends(require_roles("caregiver")),
) -> dict:
    due_at = payload.due_at.astimezone(timezone.utc)
    if due_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Waktu pengingat harus sekarang atau di masa mendatang.")

    auth_repository = request.app.state.auth_repository
    if payload.child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")
    if payload.audience == "family":
        if not auth_repository.has_linked_parent(payload.child_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Belum ada akun keluarga yang terhubung ke profil anak ini.",
            )
        recipient_ids = auth_repository.get_parent_user_ids(payload.child_id)
    else:
        recipient_ids = [user["id"]]

    records = _repository(request).create_for_recipients(
        recipient_ids=recipient_ids,
        child_id=payload.child_id,
        category="reminder",
        title=payload.title,
        body=payload.body,
        created_by=user["id"],
        dedupe_key=f"reminder:{uuid4().hex}",
        due_at=due_at.isoformat(timespec="seconds"),
    )
    if not records:
        raise HTTPException(status_code=409, detail="Pengingat belum memiliki penerima.")

    chat_events = []
    if payload.audience == "family":
        contacts = auth_repository.get_chat_contacts_for_child(user["id"], payload.child_id)
        sender = {"id": user["id"], "name": user["name"], "role": user["role"]}
        text = f"Pengingat daycare: {payload.title}. {payload.body}"
        chat_events = request.app.state.message_repository.create_event_for_recipients(
            child_id=payload.child_id,
            sender=sender,
            recipients=contacts,
            text=text,
            kind="Pengingat daycare",
        )
        for event in chat_events:
            if event["recipient_role"] != "doctor":
                continue
            _repository(request).create_for_recipients(
                recipient_ids=[event["recipient_id"]],
                child_id=payload.child_id,
                category="message",
                title="Pengingat daycare dikirim",
                body="Pengasuh menambahkan pengingat untuk keluarga. Buka percakapan untuk melihatnya.",
                created_by=user["id"],
                dedupe_key=f"reminder-chat:{records[0]['id']}",
                related_message_id=event["id"],
            )
    return {
        "notification": records[0],
        "recipient_count": len(records),
        "chat_events_created": len(chat_events),
    }


@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    request: Request,
    user: dict = Depends(require_roles("caregiver", "doctor", "parent")),
) -> dict:
    notification = _repository(request).mark_read(
        notification_id,
        user["id"],
        user.get("child_ids", []),
        user.get("organization_ids", []),
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Pemberitahuan tidak ditemukan untuk akun ini.")
    return {"notification": notification}


@router.post("/{notification_id}/complete")
def complete_reminder(
    notification_id: str,
    request: Request,
    user: dict = Depends(require_roles("caregiver", "parent")),
) -> dict:
    notification = _repository(request).complete_reminder(
        notification_id,
        user["id"],
        user.get("child_ids", []),
        user.get("organization_ids", []),
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Pengingat tidak ditemukan untuk akun ini.")
    return {"notification": notification}
