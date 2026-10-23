from fastapi.testclient import TestClient

from app.main import create_app


def test_caregiver_receives_age_aware_stimulation_recommendations(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "stimulation.sqlite3")) as client:
        authenticate(client, "caregiver")
        response = client.get("/api/development/insights/a?days=90")

        assert response.status_code == 200, response.text
        payload = response.json()
        bundle = payload["personalized_stimulation"]
        assert bundle["catalog_version"] == "stimulation-catalog-v1"
        assert bundle["catalog_count"] == 12
        assert len(bundle["recommendations"]) == 3
        assert all(item["min_age_months"] <= bundle["age_months"] <= item["max_age_months"] for item in bundle["recommendations"])
        assert all(item["safety"] and item["steps"] for item in bundle["recommendations"])


def test_feedback_is_stored_and_doctor_view_is_read_only(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "feedback.sqlite3")) as client:
        authenticate(client, "caregiver")
        initial = client.get("/api/development/insights/a?days=90").json()
        activity_id = initial["personalized_stimulation"]["recommendations"][0]["id"]

        saved = client.post(
            "/api/development/stimulation/a/feedback",
            json={"activity_id": activity_id, "outcome": "tertarik", "note": "Memilih mengulang dua kali."},
        )
        assert saved.status_code == 201, saved.text
        assert saved.json()["notifications_created"] == 1

        updated = client.get("/api/development/insights/a?days=90").json()
        assert updated["stimulation_feedback"][0]["activity_id"] == activity_id
        assert updated["stimulation_feedback"][0]["activity_title"]

        client.post("/api/auth/logout")
        authenticate(client, "doctor")
        doctor_notifications = client.get("/api/notifications").json()["notifications"]
        assert any(item["title"] == "Feedback aktivitas baru" for item in doctor_notifications)
        forbidden = client.post(
            "/api/development/stimulation/a/feedback",
            json={"activity_id": activity_id, "outcome": "menolak"},
        )
        assert forbidden.status_code == 403


def test_feedback_rejects_unknown_catalog_activity(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "invalid-feedback.sqlite3")) as client:
        authenticate(client, "caregiver")
        response = client.post(
            "/api/development/stimulation/a/feedback",
            json={"activity_id": "not-in-catalog", "outcome": "tertarik"},
        )
        assert response.status_code == 422
