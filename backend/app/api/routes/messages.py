from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.dependencies import require_roles
from app.models.schemas import FamilyMessageCreate


router = APIRouter(prefix="/messages", tags=["Pesan keluarga"])


def _repository(request: Request):
    return request.app.state.message_repository


def _notify_message_recipient(request: Request, message: dict, sender: dict) -> int:
    preview = message["text"][:220].strip()
    if len(message["text"]) > 220:
        preview += "…"
    notifications = request.app.state.notification_repository.create_for_recipients(
        recipient_ids=[message["recipient_id"]],
        child_id=message["child_id"],
        category="message",
        title=f"Pesan baru dari {sender['name']}",
        body=preview,
        created_by=sender["id"],
        dedupe_key=f"message:{message['id']}",
        related_message_id=message["id"],
    )
    return len(notifications)


@router.get("/contacts")
def list_message_contacts(
    request: Request,
    child_id: str = Query(min_length=1, max_length=80),
    user: dict = Depends(require_roles("caregiver", "doctor", "parent")),
) -> dict:
    auth_repository = request.app.state.auth_repository
    if child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")
    if not auth_repository.has_linked_parent(child_id):
        raise HTTPException(status_code=404, detail="Belum ada kontak keluarga yang terhubung ke profil ini.")
    contacts = auth_repository.get_chat_contacts_for_child(user["id"], child_id)
    return {"child_id": child_id, "contacts": contacts}


@router.get("")
def list_messages(
    request: Request,
    child_id: str | None = Query(default=None, min_length=1, max_length=80),
    user: dict = Depends(require_roles("caregiver", "doctor", "parent")),
) -> dict:
    if child_id and child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")
    messages = _repository(request).list_for_user(
        user["role"],
        user.get("child_ids", []),
        user["id"],
        child_filter=child_id,
        organization_ids=user.get("organization_ids", []),
    )
    return {"messages": messages}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_message(
    payload: FamilyMessageCreate,
    request: Request,
    user: dict = Depends(require_roles("caregiver", "doctor", "parent")),
) -> dict:
    auth_repository = request.app.state.auth_repository
    message_repository = _repository(request)

    if payload.recipient_id:
        if not payload.child_id:
            raise HTTPException(status_code=422, detail="Pilih profil anak untuk percakapan langsung.")
        if payload.child_id not in user.get("child_ids", []):
            raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")
        if not auth_repository.has_linked_parent(payload.child_id):
            raise HTTPException(status_code=409, detail="Belum ada akun keluarga yang terhubung ke profil ini.")
        contacts = auth_repository.get_chat_contacts_for_child(user["id"], payload.child_id)
        recipient = next((item for item in contacts if item["id"] == payload.recipient_id), None)
        if recipient is None:
            raise HTTPException(status_code=403, detail="Kontak ini tidak tersedia untuk profil anak yang dipilih.")
        message = message_repository.create_direct_message(
            child_id=payload.child_id,
            sender={"id": user["id"], "name": user["name"], "role": user["role"]},
            recipient=recipient,
            text=payload.text,
        )
        notifications_created = _notify_message_recipient(request, message, user)
        return {"message": message, "notifications_created": notifications_created}

    # Doctors use addressed direct conversations; the legacy broadcast endpoint is not
    # available to them. Staff and family replies remain scoped to linked children/orgs.
    if user["role"] == "doctor":
        raise HTTPException(status_code=422, detail="Dokter perlu memilih kontak sebelum mengirim pesan.")

    organization_ids = user.get("organization_ids", [])
    if payload.child_id:
        if payload.child_id not in user.get("child_ids", []):
            raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")
        organization_id = auth_repository.get_organization_id_for_child(payload.child_id)
        if organization_id not in organization_ids:
            raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke daycare tersebut.")
    else:
        if user["role"] != "caregiver":
            raise HTTPException(status_code=403, detail="Pesan keluarga harus terkait dengan profil anak yang terhubung.")
        if len(organization_ids) != 1:
            raise HTTPException(status_code=422, detail="Pilih profil anak untuk pesan jika akun terhubung ke beberapa daycare.")
        organization_id = organization_ids[0]

    if user["role"] == "caregiver":
        if payload.child_id and not auth_repository.has_linked_parent(payload.child_id):
            raise HTTPException(status_code=409, detail="Belum ada akun keluarga yang terhubung ke profil ini.")
        recipient_ids = (
            auth_repository.get_parent_user_ids(payload.child_id)
            if payload.child_id
            else auth_repository.get_parent_user_ids_for_all_linked_children([organization_id])
        )
        title = "Kabar baru dari daycare"
    else:
        recipient_ids = auth_repository.get_user_ids_by_role("caregiver", [organization_id])
        title = "Pesan baru dari keluarga"
    if not recipient_ids:
        raise HTTPException(status_code=409, detail="Belum ada penerima keluarga atau staf aktif di daycare ini.")

    message = message_repository.create(
        child_id=payload.child_id,
        organization_id=organization_id,
        author=user["name"],
        role=user["role"],
        text=payload.text,
        created_by=user["id"],
    )
    preview = message["text"][:220].strip()
    if len(message["text"]) > 220:
        preview += "…"
    notifications = request.app.state.notification_repository.create_for_recipients(
        recipient_ids=recipient_ids,
        child_id=payload.child_id,
        category="message",
        organization_id=organization_id,
        title=title,
        body=preview,
        created_by=user["id"],
        dedupe_key=f"message:{message['id']}",
        related_message_id=message["id"],
    )
    return {"message": message, "notifications_created": len(notifications)}
