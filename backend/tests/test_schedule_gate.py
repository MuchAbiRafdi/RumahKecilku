from fastapi.testclient import TestClient

from app.main import create_app


def test_api_does_not_allow_routine_form_before_scheduled_age(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "routine-gate.sqlite3")) as client:
        authenticate(client, "doctor")
        response = client.post(
            "/api/kpsp/assessments",
            json={
                "child_id": "a",
                "actual_age_months": 7,
                "birth_date": "2026-03-15",
                "screening_date": "2026-10-15",
                "screening_age_months": 9,
                "screening_mode": "routine",
                "status": "draft",
                "answers": {"1": "Ya"},
            },
        )
        assert response.status_code == 422
        assert "formulir tidak diisi sebelum usia itu" in response.json()["detail"]
