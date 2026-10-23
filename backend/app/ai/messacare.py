from __future__ import annotations

from datetime import datetime, timezone

from app.models.schemas import MessaCareAnnouncementRequest


def create_activity_announcement(payload: MessaCareAnnouncementRequest) -> dict[str, str | bool]:
    """Template-only demo. No external LLM is called and no clinical interpretation is added."""
    text = (
        f"Pembaruan aktivitas {payload.child_name}: {payload.title} "
        f"({payload.category}) pada sesi {payload.session}, pukul {payload.time}. "
        f"Catatan pengasuh: {payload.note} "
        "Pembaruan ini hanya catatan kegiatan, bukan penilaian perkembangan."
    )
    return {
        "text": text,
        "engine": "MessaCare template demo v0.1",
        "demo": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
