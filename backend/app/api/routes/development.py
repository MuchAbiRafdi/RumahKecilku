from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.ai.development_insights import ENGINE_VERSION, build_local_insights, summarize_observations
from app.ai.mock_activity_model import model_metadata
from app.ai.personalized_stimulation import load_catalog, recommend_stimulation
from app.api.dependencies import get_current_user, require_roles
from app.models.schemas import DevelopmentReportCreate, StimulationFeedbackCreate

router = APIRouter(prefix="/development", tags=["Development intelligence"])
LOCAL_TZ = ZoneInfo("Asia/Jakarta")


def _parent_contacts(auth_repository, child_id: str) -> list[dict[str, str]]:
    contacts = []
    for parent_id in auth_repository.get_parent_user_ids(child_id):
        parent = auth_repository.get_user(parent_id)
        if parent:
            contacts.append({"id": parent["id"], "name": parent["name"], "role": parent["role"]})
    return contacts


def _notify_published_report(request: Request, report: dict, user: dict, title: str, text: str, kind: str) -> tuple[int, int]:
    contacts = _parent_contacts(request.app.state.auth_repository, report["child_id"])
    events = request.app.state.message_repository.create_event_for_recipients(
        child_id=report["child_id"],
        sender={"id": user["id"], "name": user["name"], "role": user["role"]},
        recipients=contacts,
        text=text,
        kind=kind,
    )
    notifications_created = 0
    for event in events:
        notifications_created += len(request.app.state.notification_repository.create_for_recipients(
            recipient_ids=[event["recipient_id"]],
            child_id=report["child_id"],
            category="message",
            title=title,
            body="Dokter membagikan ringkasan untuk profil anak yang terhubung. Buka pesan atau laporan.",
            created_by=user["id"],
            dedupe_key=f"{kind}:{report['id']}:{event['recipient_id']}",
            related_message_id=event["id"],
        ))
    return len(events), notifications_created


@router.get("/model-status")
def model_status(request: Request, _user: dict = Depends(get_current_user)) -> dict:
    demo_enabled = bool(request.app.state.settings.demo_mode)
    metadata = model_metadata()
    return {
        "available": demo_enabled,
        "ml_trained": demo_enabled,
        "demo_activity_model_available": demo_enabled,
        "clinical_model_available": False,
        "local_insights_available": True,
        "local_engine": ENGINE_VERSION,
        "activity_model": metadata if demo_enabled else None,
        "ml_demo_training_examples": metadata["training_examples"] if demo_enabled else 0,
        "training_data_synthetic": True,
        "clinical_validated": False,
        "external_ai_api": False,
        "synthetic_preview_seed_enabled": bool(request.app.state.settings.demo_sample_data),
        "reason": (
            f"Model demo lokal {metadata['model']} benar-benar dilatih pada "
            f"{metadata['training_examples']} skenario aktivitas sintetis. Model hanya memilih ide aktivitas umum; "
            "tidak memprediksi atau menilai perkembangan, tidak divalidasi klinis, dan tidak memakai API AI pihak ketiga."
            if demo_enabled
            else "Insight bukti lokal tersedia. Model aktivitas demo berbasis data sintetis hanya diaktifkan pada mode demo; tidak ada model klinis tervalidasi."
        ),
        "demo_values_must_not_be_used_clinically": True,
    }


@router.get("/insights/{child_id}")
def get_local_insights(
    child_id: str,
    request: Request,
    days: int = Query(default=90, ge=30, le=100),
    user: dict = Depends(require_roles("caregiver", "doctor")),
) -> dict:
    if child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")
    today = datetime.now(LOCAL_TZ).date()
    period_start = today - timedelta(days=days - 1)
    observations = request.app.state.observation_repository.list_for_user("caregiver", user.get("child_ids", []))
    child_observations = [item for item in observations if item["child_id"] == child_id]
    child = next((item for item in request.app.state.auth_repository.list_child_profiles(user["id"], user["role"]) if item["id"] == child_id), None)
    if child is None:
        raise HTTPException(status_code=404, detail="Profil anak tidak ditemukan.")
    feedback = request.app.state.stimulation_repository.list_for_child(child_id)
    catalog_titles = {item["id"]: item["title"] for item in load_catalog()}
    feedback = [{**item, "activity_title": catalog_titles.get(item["activity_id"], item["activity_id"])} for item in feedback]
    return {
        "child_id": child_id,
        **build_local_insights(
            child_observations,
            period_start,
            today,
            synthetic_model_enabled=bool(request.app.state.settings.demo_mode),
        ),
        "personalized_stimulation": recommend_stimulation(child, child_observations, feedback),
        "stimulation_feedback": feedback,
    }


@router.post("/stimulation/{child_id}/feedback", status_code=201)
def create_stimulation_feedback(
    child_id: str,
    payload: StimulationFeedbackCreate,
    request: Request,
    user: dict = Depends(require_roles("caregiver")),
) -> dict:
    if child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")
    if payload.activity_id not in {item["id"] for item in load_catalog()}:
        raise HTTPException(status_code=422, detail="Aktivitas stimulasi tidak tersedia di katalog.")
    feedback = request.app.state.stimulation_repository.create(
        child_id=child_id,
        activity_id=payload.activity_id,
        outcome=payload.outcome,
        duration_minutes=payload.duration_minutes,
        note=payload.note,
        created_by=user["id"],
    )
    doctors = request.app.state.auth_repository.get_user_ids_by_role(
        "doctor",
        user.get("organization_ids", []),
    )
    notifications = request.app.state.notification_repository.create_for_recipients(
        recipient_ids=doctors,
        child_id=child_id,
        category="activity",
        title="Feedback aktivitas baru",
        body="Pengasuh menyimpan hasil percobaan aktivitas stimulasi. Buka Saran stimulasi untuk meninjau konteksnya.",
        created_by=user["id"],
        dedupe_key=f"stimulation-feedback:{feedback['id']}",
    )
    return {"feedback": feedback, "notifications_created": len(notifications)}


@router.get("/reports")
def list_development_reports(
    request: Request,
    child_id: str | None = None,
    user: dict = Depends(require_roles("caregiver", "doctor", "parent")),
) -> dict:
    child_ids = user.get("child_ids", [])
    if child_id and child_id not in child_ids:
        raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")
    reports = request.app.state.development_report_repository.list_for_user(user["role"], child_ids)
    if child_id:
        reports = [report for report in reports if report["child_id"] == child_id]
    return {"reports": reports}


@router.post("/reports", status_code=201)
def create_development_report(
    payload: DevelopmentReportCreate,
    request: Request,
    user: dict = Depends(require_roles("caregiver", "doctor")),
) -> dict:
    if payload.child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun ini tidak memiliki akses ke profil anak tersebut.")
    observations = request.app.state.observation_repository.list_for_user("caregiver", user.get("child_ids", []))
    child_observations = [item for item in observations if item["child_id"] == payload.child_id]
    stats = summarize_observations(child_observations, payload.period_start, payload.period_end)
    report = request.app.state.development_report_repository.create(
        child_id=payload.child_id,
        period_start=payload.period_start.isoformat(),
        period_end=payload.period_end.isoformat(),
        summary=payload.summary,
        observation_stats=stats,
        created_by=user["id"],
    )
    return {"report": report}


@router.post("/reports/{report_id}/publish")
def publish_development_report(
    report_id: str,
    request: Request,
    user: dict = Depends(require_roles("doctor")),
) -> dict:
    repository = request.app.state.development_report_repository
    existing = repository.get_by_id(report_id)
    if existing is None or existing["child_id"] not in user.get("child_ids", []):
        raise HTTPException(status_code=404, detail="Laporan perkembangan tidak ditemukan.")
    if existing["published"]:
        return {"report": existing}
    report = repository.publish(report_id, user["id"])
    if report is None:
        raise HTTPException(status_code=409, detail="Laporan belum dapat dibagikan.")
    event_count, notification_count = _notify_published_report(
        request,
        report,
        user,
        title="Laporan perkembangan dibagikan dokter",
        text="Dokter telah meninjau dan membagikan ringkasan perkembangan. Buka laporan untuk membaca catatan yang dibagikan.",
        kind="Laporan perkembangan dibagikan",
    )
    return {"report": report, "chat_events_created": event_count, "notifications_created": notification_count}
