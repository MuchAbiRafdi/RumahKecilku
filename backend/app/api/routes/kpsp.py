from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies import get_current_user, require_roles
from app.models.schemas import KpspAssessmentCreate, KpspReviewCreate
from app.services.kpsp_age import calculate_child_age, is_routine_screening_due, recommended_screening_age
from app.services.kpsp_service import (
    FORMS,
    KpspFormNotFound,
    KpspValidationError,
    get_form,
    public_schedule,
    score_assessment,
)

router = APIRouter(prefix="/kpsp", tags=["KPSP"])


@router.get("/schedules")
def get_schedules(_user: dict = Depends(require_roles("doctor"))) -> dict:
    return public_schedule()


@router.get("/forms/{age_months}")
def get_age_form(age_months: int, _user: dict = Depends(require_roles("doctor"))) -> dict:
    try:
        return get_form(age_months)
    except KpspFormNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/children/{child_id}/assessments")
def list_child_assessments(child_id: str, request: Request, user: dict = Depends(get_current_user)) -> dict:
    repository = request.app.state.kpsp_repository
    if child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")
    def attach_questionnaire(records: list[dict]) -> list[dict]:
        for record in records:
            try:
                form = get_form(record["screening_age_months"])
            except KpspFormNotFound:
                form = {"items": []}
            answers = record.get("answers") or {}
            record["questions"] = [
                {
                    "number": item["number"],
                    "question": item["question"],
                    "domains": item.get("domains") or [],
                    "answer": answers.get(str(item["number"]), answers.get(item["number"])),
                }
                for item in form["items"]
            ]
        return records

    if user["role"] == "parent":
        if child_id not in user.get("child_ids", []):
            raise HTTPException(status_code=403, detail="Profil anak ini tidak terhubung ke akun keluarga.")
        records = repository.list_published_for_child(child_id, include_answers=True)
        records = attach_questionnaire(records)
    elif user["role"] == "caregiver":
        # Pengasuh menerima hasil terbitan beserta butir dan jawaban untuk mendukung sesi.
        records = attach_questionnaire(repository.list_published_for_child(child_id, include_answers=True))
    elif user["role"] == "doctor":
        records = repository.list_for_child(child_id)
    else:
        raise HTTPException(status_code=403, detail="Peran akun ini tidak dapat membuka hasil KPSP.")
    return {"child_id": child_id, "assessments": records}


@router.post("/assessments/{assessment_id}/review")
def review_assessment(
    assessment_id: str,
    payload: KpspReviewCreate,
    request: Request,
    user: dict = Depends(require_roles("doctor")),
) -> dict:
    repository = request.app.state.kpsp_repository
    existing = repository.get_by_id(assessment_id)
    if existing is None or existing["child_id"] not in user.get("child_ids", []):
        raise HTTPException(status_code=404, detail="Hasil pemeriksaan tidak ditemukan.")
    if existing["status"] != "submitted":
        raise HTTPException(status_code=409, detail="Draft belum dapat ditinjau. Kirim pemeriksaan terlebih dahulu.")
    record = repository.save_review(assessment_id, user["id"], payload.decision, payload.note)
    if record is None:
        raise HTTPException(status_code=409, detail="Hasil pemeriksaan belum dapat ditinjau.")
    return {"assessment": record}


@router.post("/assessments/{assessment_id}/publish")
def publish_assessment(
    assessment_id: str,
    request: Request,
    user: dict = Depends(require_roles("doctor")),
) -> dict:
    repository = request.app.state.kpsp_repository
    existing = repository.get_by_id(assessment_id)
    if existing is None or existing["child_id"] not in user.get("child_ids", []):
        raise HTTPException(status_code=404, detail="Hasil pemeriksaan tidak ditemukan.")
    if not existing["reviewed"]:
        raise HTTPException(status_code=409, detail="Tinjau hasil pemeriksaan sebelum membagikannya kepada keluarga.")
    if existing["published"]:
        return {"assessment": existing}
    record = repository.publish(assessment_id, user["id"])
    if record is None:
        raise HTTPException(status_code=409, detail="Hasil pemeriksaan belum dapat dibagikan.")

    auth_repository = request.app.state.auth_repository
    recipients = []
    for parent_id in auth_repository.get_parent_user_ids(record["child_id"]):
        parent = auth_repository.get_user(parent_id)
        if parent:
            recipients.append({"id": parent["id"], "name": parent["name"], "role": parent["role"]})
    events = request.app.state.message_repository.create_event_for_recipients(
        child_id=record["child_id"],
        sender={"id": user["id"], "name": user["name"], "role": user["role"]},
        recipients=recipients,
        text="Dokter telah meninjau dan membagikan ringkasan KPSP. Buka laporan untuk membaca ringkasan yang dibagikan. Hasil KPSP adalah skrining, bukan diagnosis.",
        kind="Ringkasan KPSP dibagikan",
    )
    notification_count = 0
    for event in events:
        notification_count += len(request.app.state.notification_repository.create_for_recipients(
            recipient_ids=[event["recipient_id"]],
            child_id=record["child_id"],
            category="message",
            title="Ringkasan KPSP dibagikan dokter",
            body="Dokter membagikan ringkasan KPSP untuk profil anak yang terhubung. Buka pesan atau laporan.",
            created_by=user["id"],
            dedupe_key=f"kpsp-published:{assessment_id}:{event['recipient_id']}",
            related_message_id=event["id"],
        ))
    return {"assessment": record, "chat_events_created": len(events), "notifications_created": notification_count}


@router.post("/assessments", status_code=201)
def create_assessment(
    payload: KpspAssessmentCreate,
    request: Request,
    user: dict = Depends(require_roles("doctor")),
) -> dict:
    if payload.child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")
    try:
        form = get_form(payload.screening_age_months)
        if payload.birth_date is not None:
            exam_date = payload.screening_date or date.today()
            calculated_age = calculate_child_age(payload.birth_date, exam_date)
            if calculated_age.rounded_months != payload.actual_age_months:
                raise KpspValidationError(
                    f"Usia dari tanggal lahir adalah {calculated_age.rounded_months} bulan menurut aturan PDF; "
                    "perbarui usia profil sebelum menyimpan."
                )
        expected_screening_age = recommended_screening_age(
            payload.actual_age_months,
            payload.screening_mode,
        )
        if expected_screening_age is None:
            raise KpspValidationError(
                "Tidak ada usia KPSP yang sesuai untuk usia ini. Minta arahan tenaga kesehatan."
            )
        if payload.screening_age_months != expected_screening_age:
            raise KpspValidationError(
                f"Sesuai aturan PDF, gunakan KPSP usia {expected_screening_age} bulan untuk mode "
                f"{'rutin' if payload.screening_mode == 'routine' else 'keluhan'}."
            )
        if payload.screening_mode == "routine" and not is_routine_screening_due(payload.actual_age_months):
            raise KpspValidationError(
                f"Usia {payload.actual_age_months} bulan belum mencapai jadwal rutin. "
                f"Jadwalkan kembali pada usia {expected_screening_age} bulan; formulir tidak diisi sebelum usia itu."
            )
        score = score_assessment(
            payload.screening_age_months,
            payload.answers,
            payload.status,
        )
    except (KpspFormNotFound, KpspValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record = request.app.state.kpsp_repository.create(
        payload.model_dump(mode="json"),
        score,
        form["source_version"],
    )
    return {"assessment": record}
