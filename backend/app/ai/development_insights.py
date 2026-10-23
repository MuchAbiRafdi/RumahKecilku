from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.ai.mock_activity_model import model_metadata, recommend_activity_idea


LOCAL_TZ = ZoneInfo("Asia/Jakarta")
ENGINE_VERSION = "evidence-rules-v2"
DEMO_REFERENCE = "DEMO-SINTETIS"

ASPECTS = (
    "Motorik kasar",
    "Motorik halus",
    "Bahasa",
    "Sosial-emosional",
)
RESULTS = ("Teramati", "Belum teramati", "Belum ada kesempatan")

# These are low-risk activity ideas, not age-specific milestone criteria or therapy plans.
CAREGIVER_BASE_ACTIONS = {
    "Motorik kasar": "Sediakan area datar yang aman untuk bergerak sesuai pilihan anak; dampingi dari dekat dan singkirkan benda berbahaya.",
    "Motorik halus": "Tawarkan benda besar yang tidak mudah tertelan atau wadah lebar untuk dipindah-pindahkan; awasi sepanjang kegiatan.",
    "Bahasa": "Ajak bercakap atau melihat buku bergambar; beri jeda dan tanggapi kata, suara, maupun gestur tanpa memaksa anak berbicara.",
    "Sosial-emosional": "Tawarkan permainan bergiliran yang singkat dan pilihan sederhana; beri jeda, tanggapi perasaan, dan hentikan bila anak tidak nyaman.",
}
DOCTOR_CONTEXT_PROMPTS = {
    "Motorik kasar": "Periksa apakah konteks memberi ruang gerak yang aman dan apakah bantuan/dukungan saat perilaku dicatat ikut dijelaskan.",
    "Motorik halus": "Periksa benda yang digunakan, cara anak memegang atau memindahkannya, dan pengawasan keselamatan yang diberikan.",
    "Bahasa": "Bedakan respons yang benar-benar tercatat (kata, suara, atau gestur) dan ajakan/prompt yang mendahuluinya.",
    "Sosial-emosional": "Tinjau siapa yang berinteraksi, urutan giliran, serta tanda nyaman/tidak nyaman pada konteks tersebut.",
}


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(LOCAL_TZ).date()
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                return parsed.astimezone(LOCAL_TZ).date()
            return parsed.date()
        except ValueError:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
    return None


def _valid_period_observations(
    observations: list[dict[str, Any]],
    period_start: date,
    period_end: date,
) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for observation in observations:
        observation_date = _as_date(observation.get("created_at") or observation.get("date"))
        if observation_date is None or not (period_start <= observation_date <= period_end):
            continue
        if observation.get("aspect") not in ASPECTS or observation.get("result") not in RESULTS:
            continue
        valid.append({**observation, "_local_date": observation_date})
    return valid


def summarize_observations(
    observations: list[dict[str, Any]],
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    per_aspect: dict[str, dict[str, int]] = {
        aspect: {result: 0 for result in RESULTS}
        for aspect in ASPECTS
    }
    valid = _valid_period_observations(observations, period_start, period_end)
    for observation in valid:
        per_aspect[observation["aspect"]][observation["result"]] += 1
    return {
        "total_observations": len(valid),
        "by_aspect": per_aspect,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    }


def _nonzero_counts(counts: dict[str, int]) -> str:
    return "; ".join(f"{result}: {counts[result]}" for result in RESULTS if counts[result])


def _build_evidence_summary(
    counts: dict[str, int],
    rows: list[dict[str, Any]],
    period_start: date,
    period_end: date,
) -> tuple[str, int, str | None]:
    total = sum(counts.values())
    dates = sorted({row["_local_date"] for row in rows})
    last_date = dates[-1].isoformat() if dates else None
    if total == 0:
        return (
            f"Belum ada catatan pengamatan yang valid untuk aspek ini pada periode {period_start.isoformat()}–{period_end.isoformat()}.",
            0,
            None,
        )
    date_text = f" Terakhir dicatat {last_date}." if last_date else ""
    return (
        f"{total} catatan pada {len(dates)} hari: {_nonzero_counts(counts)}.{date_text}",
        len(dates),
        last_date,
    )


def _caregiver_actions(aspect: str, counts: dict[str, int]) -> list[str]:
    total = sum(counts.values())
    observed = counts["Teramati"]
    not_observed = counts["Belum teramati"]
    no_opportunity = counts["Belum ada kesempatan"]
    actions = [CAREGIVER_BASE_ACTIONS[aspect]]

    if total == 0:
        actions.append("Ini ide umum, belum personal. Setelah kegiatan, catat tanggal, konteks, kesempatan, dan perilaku yang benar-benar terlihat.")
    else:
        if no_opportunity:
            actions.append("Catatan ‘Belum ada kesempatan’ berarti perilaku itu belum dapat diamati dalam konteks tersebut; bila aman dan relevan, tawarkan kesempatan lain tanpa memaksa.")
        if not_observed:
            actions.append("‘Belum teramati’ bukan bukti bahwa anak tidak mampu. Bila sesuai, amati lagi pada kegiatan atau waktu yang berbeda dan catat apakah kesempatan memang tersedia.")
        if observed:
            actions.append("Gunakan perilaku yang tercatat sebagai contoh dari konteks itu saja. Bila kegiatan diulang, catat konteks dan bantuan yang diberikan; jangan mengubah hitungan menjadi label kemampuan.")
        if len(actions) == 1:
            actions.append("Coba variasi kecil yang disukai anak, beri ruang untuk memilih atau berhenti, lalu catat respons faktual tanpa menguji berulang-ulang.")

    return actions


def _doctor_actions(aspect: str, counts: dict[str, int]) -> list[str]:
    total = sum(counts.values())
    actions = [
        DOCTOR_CONTEXT_PROMPTS[aspect],
        "Tinjau contoh, konteks, kesempatan, prompt/bantuan, dan keadaan saat pengamatan bersama pengasuh atau keluarga; jumlah catatan adalah cakupan dokumentasi, bukan skor.",
        "Jika ada kekhawatiran, tentukan tindak lanjut dengan penilaian profesional dan prosedur yang sesuai. Insight lokal ini tidak membuat skrining atau diagnosis.",
    ]
    if total == 0:
        actions.insert(0, "Belum ada bukti observasi untuk aspek ini. Minta catatan faktual bila relevan; ketiadaan catatan tidak berarti ketiadaan kemampuan.")
    if counts["Belum ada kesempatan"]:
        actions.insert(0, "Perlakukan ‘Belum ada kesempatan’ sebagai data yang belum tersedia, bukan hasil negatif; pastikan konteks yang sesuai sebelum menafsirkan.")
    if counts["Belum teramati"]:
        actions.insert(0, "Klarifikasi apakah kesempatan dan kondisi pengamatan memadai; satu atau beberapa label ‘Belum teramati’ saja tidak menetapkan keterlambatan.")
    if counts["Teramati"]:
        actions.insert(0, "Pastikan perilaku, tingkat prompt/bantuan, dan konteksnya sebelum menyimpulkan apakah catatan dapat digeneralisasi.")
    return actions


def _data_needed(counts: dict[str, int]) -> list[str]:
    if sum(counts.values()) == 0:
        return [
            "Tanggal dan kegiatan/konteks pengamatan.",
            "Apakah anak mendapat kesempatan yang sesuai untuk mencoba.",
            "Perilaku spesifik yang terlihat atau belum terlihat serta prompt/bantuan yang diberikan.",
        ]
    needed = ["Jika kegiatan diulang, catat konteks, kesempatan, respons faktual, dan bantuan yang diberikan."]
    if counts["Belum ada kesempatan"]:
        needed.insert(0, "Kesempatan aman dan relevan pada kegiatan lain, bila tersedia.")
    if counts["Belum teramati"]:
        needed.insert(0, "Kondisi dan kesempatan pengamatan yang berbeda, tanpa memaksa anak.")
    if counts["Teramati"]:
        needed.append("Apakah perilaku terjadi spontan atau setelah ajakan/bantuan.")
    return needed


def _recommendation(aspect: str, counts: dict[str, int]) -> str:
    total = sum(counts.values())
    base = CAREGIVER_BASE_ACTIONS[aspect]
    if total == 0:
        return f"Belum ada data yang mendasari saran personal. Sebagai ide umum: {base}"
    if counts["Teramati"] and (counts["Belum teramati"] or counts["Belum ada kesempatan"]):
        return "Catatan berisi hasil yang berbeda atau kesempatan yang belum tersedia. Jangan menyederhanakannya menjadi pola kemampuan; catat konteks masing-masing dan tawarkan kesempatan yang sesuai."
    if counts["Belum ada kesempatan"]:
        return "Belum ada kesempatan tercatat untuk mengamati perilaku ini. Bila aman dan relevan, sediakan kegiatan yang memberi kesempatan; jangan menilai kemampuan dari data yang belum ada."
    if counts["Belum teramati"]:
        return "Ada catatan ‘Belum teramati’; itu bukan bukti ketidakmampuan atau keterlambatan. Bila sesuai, amati pada konteks lain dan catat kesempatan serta dukungan yang diberikan."
    return f"Ada {counts['Teramati']} catatan ‘Teramati’ pada konteks tertentu. Gunakan sebagai titik awal kegiatan, bukan kesimpulan kemampuan umum. {base}"


def build_local_insights(
    observations: list[dict[str, Any]],
    period_start: date,
    period_end: date,
    *,
    synthetic_model_enabled: bool = False,
) -> dict[str, Any]:
    stats = summarize_observations(observations, period_start, period_end)
    valid = _valid_period_observations(observations, period_start, period_end)
    insights: list[dict[str, Any]] = []
    for aspect in ASPECTS:
        counts = stats["by_aspect"][aspect]
        rows = [row for row in valid if row["aspect"] == aspect]
        total = sum(counts.values())
        evidence_summary, recorded_days, latest_observation_date = _build_evidence_summary(
            counts, rows, period_start, period_end
        )
        if total == 0:
            status = "Belum ada catatan untuk aspek ini pada periode terpilih. Saran umum di bawah belum personal."
        elif total == 1:
            status = "Satu catatan menggambarkan satu kesempatan saja; belum cukup untuk membaca pola atau perubahan."
        else:
            status = f"Ada {total} catatan pada {recorded_days} hari. Jumlah catatan menunjukkan dokumentasi, bukan kemampuan atau kemajuan anak."
        if counts["Belum teramati"]:
            status += " ‘Belum teramati’ tidak membuktikan keterlambatan."
        if counts["Belum ada kesempatan"]:
            status += " ‘Belum ada kesempatan’ bukan hasil negatif."

        insights.append(
            {
                "aspect": aspect,
                "observation_count": total,
                "observed_count": counts["Teramati"],
                "not_observed_count": counts["Belum teramati"],
                "no_opportunity_count": counts["Belum ada kesempatan"],
                "recorded_days": recorded_days,
                "latest_observation_date": latest_observation_date,
                "evidence_summary": evidence_summary,
                "status": status,
                "recommendation": _recommendation(aspect, counts),
                "model_activity_idea": (
                    recommend_activity_idea(aspect, counts)
                    if synthetic_model_enabled
                    else None
                ),
                "caregiver_actions": _caregiver_actions(aspect, counts),
                "doctor_actions": _doctor_actions(aspect, counts),
                "data_needed": _data_needed(counts),
            }
        )

    synthetic_count = sum(
        1
        for observation in valid
        if observation.get("reference") == DEMO_REFERENCE
        or str(observation.get("note") or "").startswith("DATA SINTETIS DEMO:")
    )
    activity_model = model_metadata() if synthetic_model_enabled else None
    method = (
        "Ringkasan bukti memakai aturan lokal deterministik dan dapat ditinjau; hanya memakai observasi milestone terstruktur, bukan aktivitas harian atau jawaban KPSP mentah. Tidak memakai API AI pihak ketiga."
    )
    if activity_model:
        method += (
            f" Ide kegiatan nonklinis dipilih oleh model lokal {activity_model['model']} "
            f"({activity_model['model_type']}) yang dilatih dari {activity_model['training_examples']} "
            "skenario aktivitas sintetis. Model ini tidak dilatih atau divalidasi untuk menilai perkembangan, "
            "dan bukan diagnosis, skrining, prediksi, atau rencana terapi."
        )
    return {
        "engine": ENGINE_VERSION,
        "method": method,
        "activity_model": activity_model,
        "ml_demo_enabled": bool(activity_model),
        "ml_demo_training_examples": activity_model["training_examples"] if activity_model else 0,
        "period_start": stats["period_start"],
        "period_end": stats["period_end"],
        "total_observations": stats["total_observations"],
        "synthetic_observation_count": synthetic_count,
        "synthetic_demo_notice": (
            f"{synthetic_count} catatan bertanda DATA SINTETIS DEMO bukan data anak nyata. Catatan preview ini tidak dipakai untuk melatih model; model aktivitas demo dilatih terpisah dari {activity_model['training_examples']} skenario mock sintetis dan hanya memilih ide kegiatan nonklinis."
            if synthetic_count and activity_model
            else (
                f"{synthetic_count} catatan bertanda DATA SINTETIS DEMO hanya untuk pengujian tampilan/aturan. Catatan ini bukan data anak nyata dan tidak dipakai melatih model atau membuat klaim klinis."
                if synthetic_count
                else None
            )
        ),
        "trend_estimate": "Tidak dibuat: frekuensi catatan saja tidak cukup untuk mengestimasi perkembangan anak.",
        "insights": insights,
        "clinical_boundary": "Bukan diagnosis, bukan skrining, bukan terapi, dan bukan pengganti KPSP atau penilaian tenaga kesehatan. Tinjauan dan tindak lanjut klinis tetap tanggung jawab dokter.",
    }
