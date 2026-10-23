from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "stimulation_activities.json"
ASPECTS = ("Motorik kasar", "Motorik halus", "Bahasa", "Sosial-emosional")


def load_catalog() -> list[dict[str, Any]]:
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _age_months(birth_date: str | None, today: date | None = None) -> int | None:
    if not birth_date:
        return None
    try:
        born = date.fromisoformat(birth_date[:10])
    except ValueError:
        return None
    current = today or date.today()
    return max(0, (current.year - born.year) * 12 + current.month - born.month - (current.day < born.day))


def recommend_stimulation(
    child: dict[str, Any],
    observations: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    *,
    limit: int = 3,
) -> dict[str, Any]:
    age = _age_months(child.get("birth_date"))
    counts = {aspect: {"Teramati": 0, "Belum teramati": 0, "Belum ada kesempatan": 0} for aspect in ASPECTS}
    for row in observations:
        if row.get("aspect") in counts and row.get("result") in counts[row["aspect"]]:
            counts[row["aspect"]][row["result"]] += 1
    recent_feedback = {row["activity_id"]: row for row in feedback}
    candidates = []
    for activity in load_catalog():
        if age is not None and not (activity["min_age_months"] <= age <= activity["max_age_months"]):
            continue
        aspect_counts = counts[activity["aspect"]]
        total = sum(aspect_counts.values())
        score = 0.0
        if total == 0:
            reason = "Belum ada catatan pada aspek ini; aktivitas dipilih untuk membuka kesempatan pengamatan yang aman."
            score += 3
        else:
            score += aspect_counts["Belum ada kesempatan"] * 2.5
            score += aspect_counts["Belum teramati"] * 2
            score += aspect_counts["Teramati"] * 0.5
            if aspect_counts["Belum ada kesempatan"] or aspect_counts["Belum teramati"]:
                reason = "Aspek ini memiliki catatan yang belum memberi kesempatan atau belum terlihat; ulangi dalam konteks berbeda tanpa memaksa."
            else:
                reason = "Aktivitas ini melanjutkan kesempatan yang pernah tercatat pada aspek yang sama dengan variasi kecil."
        previous = recent_feedback.get(activity["id"])
        if previous:
            score += 2 if previous.get("outcome") in {"tertarik", "sebagian"} else -1
            if previous.get("outcome") == "menolak":
                reason = "Dipilih sebagai variasi setelah percobaan sebelumnya belum cocok; berikan pilihan untuk berhenti."
        candidates.append({
            **activity,
            "score": round(score, 2),
            "reason": reason,
            "age_months": age,
            "data_basis": {"aspect": activity["aspect"], "counts": aspect_counts, "previous_feedback": previous},
        })
    candidates.sort(key=lambda item: (-item["score"], item["id"]))
    selected = []
    seen_aspects: set[str] = set()
    for item in candidates:
        if item["aspect"] not in seen_aspects or len(selected) >= limit - 1:
            selected.append(item)
            seen_aspects.add(item["aspect"])
        if len(selected) == limit:
            break
    return {
        "catalog_version": "stimulation-catalog-v1",
        "age_months": age,
        "recommendations": selected,
        "catalog_count": len(load_catalog()),
        "method": "Filter usia dan keselamatan, lalu ranking transparan berdasarkan cakupan observasi dan feedback kegiatan; bukan model klinis.",
        "boundary": "Saran ini adalah ide aktivitas nonklinis, bukan diagnosis, skrining, terapi, atau ukuran kemampuan anak.",
    }
