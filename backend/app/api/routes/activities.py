from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, Request

from app.ai.messacare import create_activity_announcement
from app.api.dependencies import require_roles
from app.models.schemas import DaycareActivityCreate, MessaCareAnnouncementRequest


router = APIRouter(prefix="/activities", tags=["Aktivitas"])


def _repository(request: Request):
    return request.app.state.activity_repository


@router.get("")
def list_activities(
    request: Request,
    user: dict = Depends(require_roles("caregiver", "doctor", "parent")),
) -> dict:
    return {"activities": _repository(request).list_for_user(user["role"], user.get("child_ids", []))}


@router.get("/{activity_id}/photo")
def get_activity_photo(
    activity_id: str,
    request: Request,
    user: dict = Depends(require_roles("caregiver", "doctor", "parent")),
) -> dict:
    image = _repository(request).get_photo(activity_id, user["role"], user.get("child_ids", []))
    if image is None:
        # Avoid confirming whether an unshared photo exists to an unrelated family account.
        raise HTTPException(status_code=404, detail="Foto tidak ditemukan atau belum dibagikan.")
    content, content_type = image
    return {
        "content_type": content_type,
        "data_url": f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}",
    }


@router.post("")
def create_activity(
    payload: DaycareActivityCreate,
    request: Request,
    user: dict = Depends(require_roles("caregiver")),
) -> dict:
    if payload.child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")

    # Bulk logging may include children without a family account. Keep the activity
    # internal for those children, while sharing it for each child that has a
    # verified parent link.
    share_to_parent = payload.share_to_parent and request.app.state.auth_repository.has_linked_parent(payload.child_id)
    payload = payload.model_copy(update={"share_to_parent": share_to_parent})
    announcement = None
    if payload.share_to_parent:
        announcement = create_activity_announcement(
            MessaCareAnnouncementRequest(
                child_name=payload.child_name,
                category=payload.category,
                title=payload.title,
                note=payload.note,
                session=payload.session,
                time=payload.time,
            )
        )

    meal_snapshot = None
    selections = [item.model_dump() for item in payload.meal_items]
    if payload.meal_id:
        selections = [{"meal_id": payload.meal_id, "servings": payload.meal_servings}]
    if selections:
        item_snapshots = []
        total_nutrition = {
            "energy_kcal": 0.0,
            "protein_g": 0.0,
            "carbohydrate_g": 0.0,
            "fat_g": 0.0,
            "fiber_g": 0.0,
        }
        total_grams = 0.0
        allergens = []
        for selection in selections:
            meal = request.app.state.meal_repository.get_active(selection["meal_id"], user.get("organization_ids", []))
            if meal is None:
                raise HTTPException(status_code=404, detail="Salah satu menu tidak ditemukan atau tidak aktif.")
            servings = selection["servings"]
            nutrition = {
                "energy_kcal": round(meal["energy_kcal"] * servings, 2),
                "protein_g": round(meal["protein_g"] * servings, 2),
                "carbohydrate_g": round(meal["carbohydrate_g"] * servings, 2),
                "fat_g": round(meal["fat_g"] * servings, 2),
                "fiber_g": round(meal["fiber_g"] * servings, 2),
            }
            for key in total_nutrition:
                total_nutrition[key] += nutrition[key]
            total_grams += meal["serving_grams"] * servings
            if meal["allergens"] and meal["allergens"] not in allergens:
                allergens.append(meal["allergens"])
            item_snapshots.append({
                "id": meal["id"],
                "name": meal["name"],
                "serving_label": meal["serving_label"],
                "serving_grams": meal["serving_grams"],
                "servings": servings,
                "total_grams": round(meal["serving_grams"] * servings, 1),
                "allergens": meal["allergens"],
                "nutrition": nutrition,
            })
        rounded_total = {key: round(value, 2) for key, value in total_nutrition.items()}
        first_item = item_snapshots[0]
        meal_snapshot = {
            "id": first_item["id"],
            "name": " + ".join(item["name"] for item in item_snapshots),
            "serving_label": f"Gabungan {len(item_snapshots)} bahan",
            "serving_grams": round(total_grams, 1),
            "servings": 1,
            "allergens": "; ".join(allergens),
            "nutrition": rounded_total,
            "items": item_snapshots,
        }

    activity = _repository(request).create(
        payload.model_dump(),
        announcement,
        user["id"],
        meal_snapshot=meal_snapshot,
    )
    auth_repository = request.app.state.auth_repository
    notification_repository = request.app.state.notification_repository
    sender = {"id": user["id"], "name": user["name"], "role": user["role"]}
    contacts = auth_repository.get_chat_contacts_for_child(user["id"], payload.child_id)
    special_case = payload.category == "Kejadian" or payload.mood == "Membutuhkan dukungan"
    if special_case:
        doctor_ids = [contact["id"] for contact in contacts if contact["role"] == "doctor"]
        notification_repository.create_for_recipients(
            recipient_ids=doctor_ids,
            child_id=payload.child_id,
            category="message",
            title="Kasus khusus perlu diperiksa",
            body=f"Ada catatan khusus untuk {payload.child_name}: {payload.title}.",
            created_by=user["id"],
            dedupe_key=f"special-case:{activity['id']}",
            related_activity_id=activity["id"],
        )
    is_photo = bool(payload.photo_data_url)
    is_media = bool(payload.photo_data_url or payload.media_data_url)
    if payload.share_to_parent:
        parent_ids = auth_repository.get_parent_user_ids(payload.child_id)
        notifications = notification_repository.create_for_recipients(
            recipient_ids=parent_ids,
            child_id=payload.child_id,
            category="photo" if is_media else "activity",
            title="Media kegiatan dibagikan" if is_media else "Catatan kegiatan dibagikan",
            body=(
                "Pengasuh membagikan foto atau video kegiatan. Buka catatan aktivitas untuk melihatnya."
                if is_media
                else f"Pengasuh membagikan catatan kegiatan: {payload.title}."
            ),
            created_by=user["id"],
            dedupe_key=f"activity:{activity['id']}",
            related_activity_id=activity["id"],
        )
        chat_events = request.app.state.message_repository.create_event_for_recipients(
            child_id=payload.child_id,
            sender=sender,
            recipients=contacts,
            text=announcement["text"],
            kind="Media kegiatan dibagikan" if is_media else "Kegiatan dibagikan",
            related_activity_id=activity["id"],
        )
        for event in chat_events:
            if event["recipient_role"] != "doctor":
                continue
            notification_repository.create_for_recipients(
                recipient_ids=[event["recipient_id"]],
                child_id=payload.child_id,
                category="message",
                title="Kegiatan dibagikan untuk keluarga",
                body="Pengasuh membagikan pembaruan kegiatan. Buka percakapan untuk melihat kabar yang dibagikan.",
                created_by=user["id"],
                dedupe_key=f"activity-chat:{activity['id']}",
                related_activity_id=activity["id"],
                related_message_id=event["id"],
            )
    else:
        # Internal activity changes may notify the clinical team, never the family.
        doctor_contacts = [contact for contact in contacts if contact["role"] == "doctor"]
        chat_events = request.app.state.message_repository.create_event_for_recipients(
            child_id=payload.child_id,
            sender=sender,
            recipients=doctor_contacts,
            text="Perubahan catatan tim baru tersimpan untuk profil ini. Isi internal tidak dibagikan ke keluarga.",
            kind="Perubahan catatan tim tersimpan",
            related_activity_id=activity["id"],
        )
        for event in chat_events:
            notification_repository.create_for_recipients(
                recipient_ids=[event["recipient_id"]],
                child_id=payload.child_id,
                category="message",
                title="Perubahan catatan tim tersimpan",
                body="Ada perubahan catatan tim yang tidak dibagikan ke keluarga. Buka ruang kerja bila Anda berwenang.",
                created_by=user["id"],
                dedupe_key=f"activity-internal:{activity['id']}",
                related_activity_id=activity["id"],
                related_message_id=event["id"],
            )
        notifications = []
    return {
        "activity": activity,
        "announcement": announcement,
        "notifications_created": len(notifications),
        "chat_events_created": len(chat_events),
    }
