from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.services.kpsp_age import SCHEDULE_MONTHS


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "kpsp_forms.json"


class KpspFormNotFound(ValueError):
    pass


class KpspValidationError(ValueError):
    pass


def load_forms() -> dict[int, dict[str, Any]]:
    with DATA_PATH.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    return {int(form["age_months"]): form for form in payload["forms"]}


FORMS = load_forms()


def get_form(age_months: int) -> dict[str, Any]:
    try:
        return FORMS[age_months]
    except KeyError as exc:
        raise KpspFormNotFound(f"Form KPSP usia {age_months} bulan tidak tersedia.") from exc


def public_schedule() -> dict[str, Any]:
    return {
        "ages_months": SCHEDULE_MONTHS,
        "rounding_rule": "Hitung umur dari tanggal lahir. Bila sisa umur lebih dari 16 hari, bulatkan naik 1 bulan; 16 hari atau kurang tidak dibulatkan.",
        "routine_rule": "Jika anak belum mencapai usia skrining, minta keluarga datang kembali pada usia skrining terdekat berikutnya (contoh PDF: usia 7 bulan → datang kembali pada 9 bulan); jangan isi formulir lebih awal. Jika tepat pada usia skrining, gunakan formulir itu.",
        "concern_rule": "Jika orang tua datang dengan keluhan dan usia anak bukan usia skrining, gunakan usia skrining terdekat yang lebih muda. Jika tidak ada usia yang lebih muda (di bawah 3 bulan), konsultasikan ke tenaga kesehatan.",
        "interpretation": [
            {"code": "S", "yes_min": 9, "yes_max": 10, "label": "Sesuai dengan tahap perkembangannya (S)"},
            {"code": "M", "yes_min": 7, "yes_max": 8, "label": "Meragukan (M)"},
            {"code": "P", "yes_min": 0, "yes_max": 6, "label": "Kemungkinan ada penyimpangan (P)"},
        ],
        "answer_guide": {
            "Ya": "Anak bisa, pernah, sering, atau kadang-kadang melakukan kemampuan tersebut.",
            "Tidak": "Anak belum pernah/tidak pernah melakukannya, atau pengasuh tidak tahu.",
        },
        "notice": "Interpretasi ini mengikuti PDF KPSP dan merupakan hasil skrining, bukan diagnosis.",
    }


def score_assessment(age_months: int, answers: dict[int, str], status: str) -> dict[str, Any]:
    form = get_form(age_months)
    item_numbers = {int(item["number"]) for item in form["items"]}
    unknown = set(answers) - item_numbers
    if unknown:
        raise KpspValidationError(f"Nomor butir tidak dikenali: {', '.join(map(str, sorted(unknown)))}.")

    if status == "submitted" and set(answers) != item_numbers:
        missing = sorted(item_numbers - set(answers))
        raise KpspValidationError(f"Jawab semua butir sebelum dikirim. Belum dijawab: {', '.join(map(str, missing))}.")

    yes_count = sum(1 for answer in answers.values() if answer == "Ya")
    answered_count = len(answers)
    complete = answered_count == len(item_numbers)
    result_code = None
    result_label = None
    no_by_domain: Counter[str] = Counter()
    uncategorized_no = 0

    if complete and status == "submitted":
        if yes_count >= 9:
            result_code = "S"
            result_label = "Sesuai dengan tahap perkembangannya (S)"
        elif yes_count >= 7:
            result_code = "M"
            result_label = "Meragukan (M)"
        else:
            result_code = "P"
            result_label = "Kemungkinan ada penyimpangan (P)"

        for item in form["items"]:
            number = int(item["number"])
            if answers.get(number) != "Tidak":
                continue
            domains = item.get("domains") or []
            if not domains:
                uncategorized_no += 1
            else:
                for domain in domains:
                    no_by_domain[domain] += 1

    return {
        "total_items": len(item_numbers),
        "answered_count": answered_count,
        "yes_count": yes_count if complete else None,
        "no_count": (len(item_numbers) - yes_count) if complete else None,
        "result_code": result_code,
        "result_label": result_label,
        "no_by_domain": dict(no_by_domain),
        "uncategorized_no_count": uncategorized_no,
        "is_complete": complete,
        "interpretation_notice": "Hasil skrining KPSP sesuai PDF; bukan diagnosis dan perlu ditafsirkan oleh tenaga kesehatan.",
    }
