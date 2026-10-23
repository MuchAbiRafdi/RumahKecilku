"""Demo-only, local ML model for selecting a nonclinical activity-idea category.

The model is trained in memory from a bundled, explicitly synthetic scenario set.
It is not a developmental assessment, prediction, screener, or clinical tool.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from math import log
from pathlib import Path
from typing import Any

MODEL_ID = "mock-activity-nb-v1"
MODEL_NAME = "Multinomial Naive Bayes"
DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "mock_activity_training.json"

_ACTIVITY_IDEAS = {
    "Motorik kasar": {
        "general_idea": "Sebagai ide umum, sediakan area datar yang aman untuk bergerak sesuai pilihan anak; dampingi dan singkirkan benda berbahaya.",
        "repeat_variation": "Ulangi permainan gerak yang disukai dengan variasi kecil pada posisi atau benda, hanya bila aman dan anak nyaman.",
        "alternate_context": "Bila sesuai, coba kegiatan gerak pada waktu atau ruang aman yang berbeda; catat kesempatan dan bantuan, bukan kesimpulan kemampuan.",
        "create_opportunity": "Tawarkan kesempatan bergerak di area datar yang aman dan bebas hambatan; dampingi tanpa meminta anak melakukan gerakan tertentu.",
        "compare_contexts": "Bandingkan konteks, kesempatan, dan bantuan pada catatan yang berbeda; pilih permainan gerak ringan yang disukai anak.",
    },
    "Motorik halus": {
        "general_idea": "Sebagai ide umum, tawarkan benda besar dan aman untuk dipindahkan atau wadah lebar; awasi sepanjang kegiatan.",
        "repeat_variation": "Ulangi permainan memindahkan benda besar yang aman dengan wadah atau posisi berbeda; tetap awasi dan ikuti minat anak.",
        "alternate_context": "Bila sesuai, coba benda besar yang aman pada kegiatan atau waktu berbeda; catat kesempatan dan bantuan yang diberikan.",
        "create_opportunity": "Siapkan benda besar yang tidak mudah tertelan dan wadah lebar agar ada kesempatan mencoba; awasi terus.",
        "compare_contexts": "Bandingkan benda, permukaan, kesempatan, dan bantuan di tiap konteks; pilih permainan manipulatif yang aman dan sederhana.",
    },
    "Bahasa": {
        "general_idea": "Sebagai ide umum, lihat buku bergambar atau bercakap santai; beri jeda dan tanggapi kata, suara, maupun gestur tanpa memaksa.",
        "repeat_variation": "Ulangi percakapan atau buku bergambar yang disukai dengan jeda untuk respons; tanggapi kata, suara, dan gestur tanpa menguji.",
        "alternate_context": "Bila sesuai, ajak bercakap saat rutinitas lain; catat kata, suara, atau gestur dan ajakan yang mendahuluinya.",
        "create_opportunity": "Ciptakan kesempatan komunikasi lewat pilihan sederhana atau buku bergambar; beri waktu dan terima respons verbal maupun gestur.",
        "compare_contexts": "Bandingkan kegiatan, ajakan, dan bentuk respons yang tercatat; jangan menilai kemampuan bahasa dari hitungan catatan.",
    },
    "Sosial-emosional": {
        "general_idea": "Sebagai ide umum, tawarkan permainan bergiliran singkat dan pilihan sederhana; beri jeda dan hentikan bila anak tidak nyaman.",
        "repeat_variation": "Ulangi permainan bergiliran yang disukai dengan perubahan kecil; ikuti isyarat anak dan beri kesempatan untuk berhenti.",
        "alternate_context": "Bila sesuai, tawarkan interaksi singkat dengan orang atau rutinitas berbeda; catat konteks dan tanda nyaman/tidak nyaman.",
        "create_opportunity": "Sediakan permainan bergiliran sederhana dengan orang yang akrab; ikuti pilihan anak dan hentikan bila ia tidak nyaman.",
        "compare_contexts": "Bandingkan siapa yang berinteraksi, urutan giliran, dan tanda nyaman pada tiap catatan; pilih kegiatan yang disukai anak.",
    },
}


def _features(example: dict[str, Any]) -> tuple[str, ...]:
    return (
        f"aspect:{example['aspect']}",
        f"state:{example['evidence_state']}",
        f"count:{example['count_band']}",
    )


class _MultinomialNaiveBayes:
    """Small pure-Python multinomial Naive Bayes classifier."""

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self.class_documents: Counter[str] = Counter()
        self.class_tokens: dict[str, Counter[str]] = defaultdict(Counter)
        self.class_token_totals: Counter[str] = Counter()
        self.vocabulary: set[str] = set()
        self.total_documents = 0

    def fit(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            raise ValueError("Synthetic activity training dataset is empty")
        for row in rows:
            if row.get("synthetic") is not True:
                raise ValueError("The demo model accepts explicitly synthetic rows only")
            label = str(row["activity_idea_label"])
            tokens = _features(row)
            self.class_documents[label] += 1
            self.total_documents += 1
            self.class_tokens[label].update(tokens)
            self.class_token_totals[label] += len(tokens)
            self.vocabulary.update(tokens)
        if not self.vocabulary:
            raise ValueError("Synthetic activity training dataset has no usable features")

    def predict(self, example: dict[str, Any]) -> str:
        tokens = _features(example)
        vocab_size = max(1, len(self.vocabulary))
        scored: list[tuple[float, str]] = []
        for label, document_count in self.class_documents.items():
            score = log(document_count / self.total_documents)
            denominator = self.class_token_totals[label] + self.alpha * vocab_size
            for token in tokens:
                if token not in self.vocabulary:
                    continue
                numerator = self.class_tokens[label][token] + self.alpha
                score += log(numerator / denominator)
            scored.append((score, label))
        return max(scored)[1]


def _load_and_train() -> tuple[_MultinomialNaiveBayes, dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    metadata = payload.get("metadata") or {}
    rows = payload.get("examples") or []
    if metadata.get("synthetic") is not True or metadata.get("child_records_used") is not False:
        raise ValueError("Activity model training data must be synthetic and independent of child records")
    if metadata.get("clinical_labels") is not False:
        raise ValueError("Clinical labels are not allowed in the activity demo dataset")
    model = _MultinomialNaiveBayes()
    model.fit(rows)
    return model, metadata, rows


_MODEL, _DATASET_METADATA, _TRAINING_ROWS = _load_and_train()
TRAINING_EXAMPLE_COUNT = len(_TRAINING_ROWS)


def _evidence_state(counts: dict[str, int]) -> str:
    result_counts = {
        "observed": int(counts.get("Teramati", 0) or 0),
        "not_observed": int(counts.get("Belum teramati", 0) or 0),
        "no_opportunity": int(counts.get("Belum ada kesempatan", 0) or 0),
    }
    active_states = [state for state, count in result_counts.items() if count > 0]
    if not active_states:
        return "no_data"
    if len(active_states) > 1:
        return "mixed"
    return active_states[0]


def _count_band(counts: dict[str, int]) -> str:
    total = sum(int(value or 0) for value in counts.values())
    if total == 0:
        return "none"
    return "single" if total == 1 else "multiple"


def recommend_activity_idea(aspect: str, counts: dict[str, int]) -> dict[str, Any]:
    """Return an activity idea chosen by the locally trained demo classifier.

    It uses only the structured aspect/result counts passed by the caller. The
    classifier output is limited to a static, low-risk nonclinical activity idea.
    """
    if aspect not in _ACTIVITY_IDEAS:
        raise ValueError("Unsupported aspect")
    example = {
        "aspect": aspect,
        "evidence_state": _evidence_state(counts),
        "count_band": _count_band(counts),
    }
    label = _MODEL.predict(example)
    # Fail closed to an unpersonalized, general idea if the model ever returns an
    # unsupported class; otherwise the trained classifier selects the category.
    if label not in _ACTIVITY_IDEAS[aspect]:
        label = "general_idea"
    return {
        "model": MODEL_ID,
        "model_type": MODEL_NAME,
        "training_source": "synthetic mock activity scenarios",
        "training_examples": TRAINING_EXAMPLE_COUNT,
        "model_features": ["aspect", "evidence_state", "count_band"],
        "synthetic_training_data": True,
        "label": label,
        "text": _ACTIVITY_IDEAS[aspect][label],
        "scope": "Selects a general activity idea only; not a developmental assessment, prediction, diagnosis, screening, or treatment recommendation.",
    }


def model_metadata() -> dict[str, Any]:
    return {
        "model": MODEL_ID,
        "model_type": MODEL_NAME,
        "training_source": "synthetic mock activity scenarios",
        "training_examples": TRAINING_EXAMPLE_COUNT,
        "model_features": ["aspect", "evidence_state", "count_band"],
        "synthetic_training_data": True,
        "clinical_labels": False,
        "clinical_validation": False,
        "child_records_used_for_training": False,
        "external_ai_api": False,
        "scope": "Selects a general activity idea only; not a developmental assessment, prediction, diagnosis, screening, or treatment recommendation.",
    }
