import json
from pathlib import Path

from app.ai.mock_activity_model import (
    DATASET_PATH,
    MODEL_ID,
    TRAINING_EXAMPLE_COUNT,
    model_metadata,
    recommend_activity_idea,
)


def test_training_data_is_synthetic_and_has_no_clinical_outcomes():
    payload = json.loads(Path(DATASET_PATH).read_text(encoding="utf-8"))
    metadata = payload["metadata"]
    examples = payload["examples"]

    assert MODEL_ID == "mock-activity-nb-v1"
    assert len(examples) == TRAINING_EXAMPLE_COUNT == 96
    assert metadata["synthetic"] is True
    assert metadata["clinical_labels"] is False
    assert metadata["child_records_used"] is False
    assert metadata["model_features"] == ["aspect", "evidence_state", "count_band"]
    assert metadata["context_family_is_model_input"] is False
    assert all(example["synthetic"] is True for example in examples)
    assert all("child_id" not in example and "name" not in example for example in examples)


def test_trained_classifier_selects_only_activity_idea_categories():
    cases = (
        ({}, "general_idea"),
        ({"Teramati": 1}, "repeat_variation"),
        ({"Belum teramati": 1}, "alternate_context"),
        ({"Belum ada kesempatan": 1}, "create_opportunity"),
        ({"Teramati": 1, "Belum teramati": 1}, "compare_contexts"),
    )
    for counts, expected_label in cases:
        prediction = recommend_activity_idea("Bahasa", counts)
        assert prediction["label"] == expected_label
        assert prediction["model"] == MODEL_ID
        assert prediction["training_examples"] == 96
        assert prediction["synthetic_training_data"] is True
        assert prediction["text"]
        assert "diagnosis" in prediction["scope"]
        assert "not a developmental assessment" in prediction["scope"]


def test_model_metadata_discloses_no_clinical_validation_or_external_ai():
    metadata = model_metadata()
    assert metadata["clinical_validation"] is False
    assert metadata["clinical_labels"] is False
    assert metadata["child_records_used_for_training"] is False
    assert metadata["external_ai_api"] is False
