from datetime import date

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.kpsp_age import calculate_child_age, is_routine_screening_due, recommended_screening_age
from app.services.kpsp_service import get_form, score_assessment


def test_catalog_has_all_pdf_age_groups_and_correct_item_counts():
    expected = [3, 6, 9, 12, 15, 18, 21, 24, 30, 36, 42, 48, 54, 60, 66, 72]
    from app.services.kpsp_service import SCHEDULE_MONTHS

    assert list(SCHEDULE_MONTHS) == expected
    assert len(get_form(42)["items"]) == 9
    assert len(get_form(48)["items"]) == 9
    assert all(len(get_form(age)["items"]) == 10 for age in expected if age not in {42, 48})


def test_24_month_pdf_domain_cells_remain_blank_for_items_six_to_ten():
    form = get_form(24)
    assert all(item["domains"] == [] for item in form["items"] if int(item["number"]) >= 6)


def test_kpsp_thresholds_are_based_on_item_count_and_yes_answers():
    form_9 = get_form(42)
    answers_9 = {int(item["number"]): "Ya" for item in form_9["items"]}
    assert score_assessment(42, answers_9, "submitted")["result_code"] == "S"

    answers_9[9] = "Tidak"
    assert score_assessment(42, answers_9, "submitted")["result_code"] == "M"
    answers_9[8] = "Tidak"
    answers_9[7] = "Tidak"
    assert score_assessment(42, answers_9, "submitted")["result_code"] == "P"


def test_24_month_uncategorized_no_answers_are_not_assigned_to_invented_domains():
    form = get_form(24)
    answers = {int(item["number"]): "Tidak" for item in form["items"]}
    score = score_assessment(24, answers, "submitted")
    assert score["uncategorized_no_count"] == 5
    assert "Gerak kasar" in score["no_by_domain"]
    assert "Gerak halus" in score["no_by_domain"]
    assert "Bicara & bahasa" in score["no_by_domain"]
    assert "Sosialisasi & kemandirian" in score["no_by_domain"]


def test_age_rounding_uses_more_than_sixteen_days():
    age_16 = calculate_child_age(date(2024, 10, 15), date(2026, 10, 31))
    age_17 = calculate_child_age(date(2024, 10, 15), date(2026, 11, 1))
    assert (age_16.completed_months, age_16.remainder_days, age_16.rounded_months) == (24, 16, 24)
    assert (age_17.completed_months, age_17.remainder_days, age_17.rounded_months) == (24, 17, 25)


def test_pdf_selection_rules_for_routine_and_concern():
    assert recommended_screening_age(7, "routine") == 9
    assert recommended_screening_age(7, "concern") == 6
    assert recommended_screening_age(24, "routine") == 24
    assert recommended_screening_age(24, "concern") == 24
    assert recommended_screening_age(2, "routine") == 3
    assert recommended_screening_age(2, "concern") is None
    assert recommended_screening_age(73, "routine") is None
    assert is_routine_screening_due(24) is True
    assert is_routine_screening_due(7) is False


def test_api_serves_age_form_and_persists_submitted_assessment(tmp_path, authenticate):
    app = create_app(tmp_path / "kpsp-test.sqlite3")
    with TestClient(app) as client:
        authenticate(client, "doctor")
        form_response = client.get("/api/kpsp/forms/42")
        assert form_response.status_code == 200
        assert len(form_response.json()["items"]) == 9

        payload = {
            "child_id": "a",
            "actual_age_months": 24,
            "birth_date": "2024-10-15",
            "screening_date": "2026-10-15",
            "screening_age_months": 24,
            "screening_mode": "routine",
            "status": "submitted",
            "answers": {str(index): "Ya" for index in range(1, 11)},
        }
        response = client.post("/api/kpsp/assessments", json=payload)
        assert response.status_code == 201, response.text
        record = response.json()["assessment"]
        assert record["score"]["result_code"] == "S"
        assert record["score"]["total_items"] == 10
        history = client.get("/api/kpsp/children/a/assessments")
        assert history.status_code == 200
        assert len(history.json()["assessments"]) == 1


def test_kpsp_stays_private_until_doctor_reviews_and_publishes(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "kpsp-publication.sqlite3")) as client:
        authenticate(client, "doctor")
        payload = {
            "child_id": "a",
            "actual_age_months": 24,
            "birth_date": "2024-10-15",
            "screening_date": "2026-10-15",
            "screening_age_months": 24,
            "screening_mode": "routine",
            "status": "submitted",
            "answers": {str(index): "Ya" for index in range(1, 11)},
        }
        created = client.post("/api/kpsp/assessments", json=payload)
        assert created.status_code == 201, created.text
        assessment_id = created.json()["assessment"]["id"]
        assert created.json()["assessment"]["reviewed"] is False
        assert created.json()["assessment"]["published"] is False
        assert client.post(f"/api/kpsp/assessments/{assessment_id}/publish").status_code == 409

        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        assert client.get("/api/kpsp/children/a/assessments").json()["assessments"] == []
        client.post("/api/auth/logout")
        authenticate(client, "doctor")

        review = client.post(
            f"/api/kpsp/assessments/{assessment_id}/review",
            json={"decision": "Kumpulkan observasi tambahan", "note": "Tinjau bersama catatan pengasuh."},
        )
        assert review.status_code == 200, review.text
        assert review.json()["assessment"]["reviewed"] is True
        assert review.json()["assessment"]["published"] is False
        published = client.post(f"/api/kpsp/assessments/{assessment_id}/publish")
        assert published.status_code == 200, published.text
        assert published.json()["assessment"]["published"] is True
        assert published.json()["chat_events_created"] == 1
        assert published.json()["notifications_created"] == 1
        doctor_chat = client.get("/api/messages").json()["messages"]
        assert any(item["kind"] == "Ringkasan KPSP dibagikan" for item in doctor_chat)
        assert all("answers" not in item for item in doctor_chat)
        # Retrying publication must not create duplicate chat events.
        assert client.post(f"/api/kpsp/assessments/{assessment_id}/publish").status_code == 200
        assert len([item for item in client.get("/api/messages").json()["messages"] if item["kind"] == "Ringkasan KPSP dibagikan"]) == 1

        doctor_history = client.get("/api/kpsp/children/a/assessments").json()["assessments"]
        assert doctor_history[0]["answers"] == payload["answers"]
        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        caregiver_history = client.get("/api/kpsp/children/a/assessments")
        assert caregiver_history.status_code == 200
        caregiver_record = caregiver_history.json()["assessments"][0]
        assert caregiver_record["published"] is True
        assert "answers" not in caregiver_record
        client.post("/api/auth/logout")
        authenticate(client, "parent")
        family_history = client.get("/api/kpsp/children/a/assessments")
        assert family_history.status_code == 200
        record = family_history.json()["assessments"][0]
        assert record["published"] is True
        assert record["review_note"] == "Tinjau bersama catatan pengasuh."
        assert "answers" not in record
        assert set(record["score"]) == {"result_code", "result_label", "yes_count", "total_items"}
        parent_chat = client.get("/api/messages").json()["messages"]
        published_notice = next(item for item in parent_chat if item["kind"] == "Ringkasan KPSP dibagikan")
        assert "bukan diagnosis" in published_notice["text"]
        assert all("answers" not in item for item in parent_chat)
        assert any(item["related_message_id"] == published_notice["id"] for item in client.get("/api/notifications").json()["notifications"])
        assert client.get("/api/kpsp/children/b/assessments").status_code == 403
        assert client.post(
            f"/api/kpsp/assessments/{assessment_id}/review",
            json={"decision": "Kumpulkan observasi tambahan", "note": "Tidak diizinkan."},
        ).status_code == 403


def test_api_rejects_screening_age_that_breaks_pdf_selection_rule(tmp_path, authenticate):
    app = create_app(tmp_path / "kpsp-invalid-test.sqlite3")
    with TestClient(app) as client:
        authenticate(client, "doctor")
        response = client.post(
            "/api/kpsp/assessments",
            json={
                "child_id": "a",
                "actual_age_months": 7,
                "birth_date": "2026-03-15",
                "screening_date": "2026-10-15",
                "screening_age_months": 30,
                "screening_mode": "routine",
                "status": "draft",
                "answers": {"1": "Ya"},
            },
        )
        assert response.status_code == 422
        assert "gunakan KPSP usia 9 bulan" in response.json()["detail"]
