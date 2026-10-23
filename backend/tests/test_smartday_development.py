import base64
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import create_app


TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)


def test_meal_catalog_is_doctor_managed_and_nutrition_is_snapshotted(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "meal-catalog.sqlite3")) as client:
        authenticate(client, "caregiver")
        seeded_meals = client.get("/api/meals/catalog").json()["meals"]
        assert any(meal["id"] == "seed-tkpi2020-ap001" for meal in seeded_meals)
        assert client.post(
            "/api/meals/catalog",
            json={"name": "Menu tanpa izin", "serving_label": "1 porsi", "serving_grams": 150,
                  "energy_kcal": 300, "protein_g": 10, "carbohydrate_g": 45, "fat_g": 8, "fiber_g": 4},
        ).status_code == 403

        client.post("/api/auth/logout")
        authenticate(client, "doctor")
        created = client.post(
            "/api/meals/catalog",
            json={"name": "Nasi, ikan, dan sayur", "serving_label": "1 piring", "serving_grams": 180,
                  "energy_kcal": 320, "protein_g": 16, "carbohydrate_g": 48, "fat_g": 7, "fiber_g": 5,
                  "allergens": "Ikan", "notes": "Nilai contoh untuk pengujian."},
        )
        assert created.status_code == 201, created.text
        meal = created.json()["meal"]
        assert any(meal["name"] == "Nasi, ikan, dan sayur" for meal in client.get("/api/meals/catalog").json()["meals"])

        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        activity = client.post(
            "/api/activities",
            json={"child_id": "a", "child_name": "Ananda A", "category": "Makan", "title": meal["name"],
                  "note": "Menu disajikan; respons dicatat secara faktual.", "session": "Siang", "time": "12:10",
                  "meal_id": meal["id"], "meal_servings": 0.5, "share_to_parent": True},
        )
        assert activity.status_code == 200, activity.text
        snapshot = activity.json()["activity"]["meal"]
        assert snapshot["name"] == meal["name"]
        assert snapshot["nutrition"]["energy_kcal"] == 160
        assert snapshot["nutrition"]["protein_g"] == 8

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        parent_activity = client.get("/api/activities").json()["activities"]
        assert len(parent_activity) == 1
        assert parent_activity[0]["meal"]["nutrition"]["energy_kcal"] == 160


def test_activity_photo_requires_privacy_confirmation_and_is_shared_only_with_activity(tmp_path, authenticate):
    image_data_url = "data:image/png;base64," + base64.b64encode(TINY_PNG).decode("ascii")
    activity_payload = {
        "child_id": "a", "child_name": "Ananda A", "category": "Bermain", "title": "Bermain balok",
        "note": "Menyusun balok bersama pengasuh.", "session": "Pagi", "time": "09:15",
        "photo_data_url": image_data_url,
    }
    with TestClient(create_app(tmp_path / "activity-photo.sqlite3")) as client:
        authenticate(client, "caregiver")
        rejected = client.post("/api/activities", json=activity_payload)
        assert rejected.status_code == 422
        assert "persetujuan" in str(rejected.json()["detail"]).lower()

        shared = client.post(
            "/api/activities",
            json={**activity_payload, "photo_consent_confirmed": True, "share_to_parent": True},
        )
        assert shared.status_code == 200, shared.text
        shared_id = shared.json()["activity"]["id"]
        assert shared.json()["activity"]["photo_available"] is True

        private = client.post(
            "/api/activities",
            json={**activity_payload, "title": "Catatan internal", "photo_consent_confirmed": True},
        )
        assert private.status_code == 200
        private_id = private.json()["activity"]["id"]

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        assert client.get(f"/api/activities/{shared_id}/photo").status_code == 200
        assert client.get(f"/api/activities/{private_id}/photo").status_code == 404
        assert [item["id"] for item in client.get("/api/activities").json()["activities"]] == [shared_id]


def test_three_month_development_report_requires_doctor_publication_for_parent_visibility(tmp_path, authenticate):
    period_end = date.today()
    period_start = period_end - timedelta(days=90)
    start_text, end_text = period_start.isoformat(), period_end.isoformat()
    with TestClient(create_app(tmp_path / "quarterly-report.sqlite3")) as client:
        authenticate(client, "caregiver")
        observation = client.post(
            "/api/observations",
            json={"child_id": "a", "aspect": "Bahasa", "milestone": "Menunjuk gambar",
                  "reference": "", "result": "Teramati", "context": "Membaca buku bersama",
                  "note": "Menunjuk gambar saat diajak berbincang.", "time": "10:00"},
        )
        assert observation.status_code == 201, observation.text
        created = client.post(
            "/api/development/reports",
            json={"child_id": "a", "period_start": start_text, "period_end": end_text,
                  "summary": "Pada sesi membaca tercatat beberapa kesempatan menunjuk gambar."},
        )
        assert created.status_code == 201, created.text
        short_period = client.post(
            "/api/development/reports",
            json={"child_id": "a", "period_start": (period_end - timedelta(days=1)).isoformat(), "period_end": end_text, "summary": "Periode terlalu singkat."},
        )
        assert short_period.status_code == 422
        report = created.json()["report"]
        assert report["observation_stats"]["total_observations"] == 1
        assert report["observation_stats"]["by_aspect"]["Bahasa"]["Teramati"] == 1
        assert client.get("/api/development/reports").json()["reports"][0]["status"] == "draft"

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        assert client.get("/api/development/reports").json()["reports"] == []
        assert client.post("/api/development/reports", json={"child_id": "a", "period_start": start_text, "period_end": end_text, "summary": "Tidak boleh."}).status_code == 403

        client.post("/api/auth/logout")
        authenticate(client, "doctor")
        published = client.post(f"/api/development/reports/{report['id']}/publish")
        assert published.status_code == 200, published.text
        assert published.json()["report"]["published"] is True
        assert published.json()["chat_events_created"] == 1
        assert published.json()["notifications_created"] == 1
        doctor_chat = client.get("/api/messages").json()["messages"]
        assert any(item["kind"] == "Laporan perkembangan dibagikan" for item in doctor_chat)

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        visible = client.get("/api/development/reports").json()["reports"]
        assert len(visible) == 1
        assert visible[0]["summary"] == report["summary"]
        parent_chat = client.get("/api/messages").json()["messages"]
        published_notice = next(item for item in parent_chat if item["kind"] == "Laporan perkembangan dibagikan")
        assert any(item["related_message_id"] == published_notice["id"] for item in client.get("/api/notifications").json()["notifications"])


def test_local_insights_disclose_synthetic_activity_ml_and_clinical_limits(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "local-insights.sqlite3")) as client:
        authenticate(client, "caregiver")
        status = client.get("/api/development/model-status").json()
        assert status["available"] is True
        assert status["ml_trained"] is True
        assert status["demo_activity_model_available"] is True
        assert status["clinical_model_available"] is False
        assert status["clinical_validated"] is False
        assert status["training_data_synthetic"] is True
        assert status["ml_demo_training_examples"] == 96
        assert status["external_ai_api"] is False
        assert status["local_insights_available"] is True
        assert status["local_engine"] == "evidence-rules-v2"
        assert status["synthetic_preview_seed_enabled"] is False
        assert status["demo_values_must_not_be_used_clinically"] is True

        empty = client.get("/api/development/insights/a?days=90")
        assert empty.status_code == 200
        empty_payload = empty.json()
        assert empty_payload["engine"] == "evidence-rules-v2"
        assert empty_payload["ml_demo_enabled"] is True
        assert empty_payload["ml_demo_training_examples"] == 96
        assert empty_payload["activity_model"]["model"] == "mock-activity-nb-v1"
        assert empty_payload["activity_model"]["synthetic_training_data"] is True
        assert empty_payload["activity_model"]["clinical_validation"] is False
        assert empty_payload["total_observations"] == 0
        assert len(empty_payload["insights"]) == 4
        language = next(item for item in empty_payload["insights"] if item["aspect"] == "Bahasa")
        assert language["observation_count"] == 0
        assert "belum personal" in language["status"].lower()
        assert language["model_activity_idea"]["training_examples"] == 96
        assert language["model_activity_idea"]["synthetic_training_data"] is True
        assert language["model_activity_idea"]["label"] == "general_idea"
        assert language["caregiver_actions"]
        assert language["doctor_actions"]
        assert language["data_needed"]
        assert client.get("/api/development/insights/a?days=29").status_code == 422

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        assert client.get("/api/development/insights/a").status_code == 403


def test_insights_show_factual_basis_and_distinct_role_guidance(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "insight-evidence.sqlite3")) as client:
        authenticate(client, "caregiver")
        for result, context, note in (
            ("Teramati", "Membaca buku bergambar", "Menunjuk satu gambar saat diajak."),
            ("Belum teramati", "Permainan bergiliran", "Pada kesempatan ini perilaku sasaran belum terlihat."),
            ("Belum ada kesempatan", "Sesi mendengarkan cerita", "Kegiatan ini tidak memberi kesempatan untuk mencoba."),
        ):
            response = client.post(
                "/api/observations",
                json={"child_id": "a", "aspect": "Bahasa", "milestone": "Respons dalam kegiatan",
                      "reference": "", "result": result, "context": context, "note": note, "time": "10:00"},
            )
            assert response.status_code == 201, response.text

        payload = client.get("/api/development/insights/a?days=90").json()
        language = next(item for item in payload["insights"] if item["aspect"] == "Bahasa")
        assert payload["total_observations"] == 3
        assert language["observation_count"] == 3
        assert language["observed_count"] == 1
        assert language["not_observed_count"] == 1
        assert language["no_opportunity_count"] == 1
        assert language["recorded_days"] == 1
        assert "Teramati: 1" in language["evidence_summary"]
        assert "Belum teramati: 1" in language["evidence_summary"]
        assert "Belum ada kesempatan: 1" in language["evidence_summary"]
        assert "berbeda" in language["recommendation"].lower()
        assert any("bukan bukti" in action.lower() for action in language["caregiver_actions"])
        assert any("bukan hasil negatif" in action.lower() for action in language["doctor_actions"])
        assert language["data_needed"]
        assert payload["synthetic_observation_count"] == 0
        assert payload["synthetic_demo_notice"] is None
        assert "Menunjuk satu gambar saat diajak." not in str(payload)

        client.post("/api/auth/logout")
        authenticate(client, "doctor")
        doctor_payload = client.get("/api/development/insights/a?days=90").json()
        doctor_language = next(item for item in doctor_payload["insights"] if item["aspect"] == "Bahasa")
        assert doctor_language["doctor_actions"] == language["doctor_actions"]
        assert doctor_language["caregiver_actions"] == language["caregiver_actions"]
        assert client.get("/api/observations").status_code == 200


def test_synthetic_observation_seed_is_opt_in_marked_and_idempotent(tmp_path, monkeypatch, authenticate):
    database = tmp_path / "synthetic-insights.sqlite3"
    monkeypatch.setenv("RUMAH_APP_ENV", "preview")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "1")
    monkeypatch.setenv("RUMAH_DEMO_SAMPLE_DATA", "1")

    with TestClient(create_app(database)) as client:
        authenticate(client, "caregiver")
        assert client.get("/api/development/model-status").json()["synthetic_preview_seed_enabled"] is True
        observations = client.get("/api/observations").json()["observations"]
        assert len(observations) == 9
        assert all(item["reference"] == "DEMO-SINTETIS" for item in observations)
        assert all(item["context"].startswith("DEMO SINTETIS ·") for item in observations)
        assert all(item["note"].startswith("DATA SINTETIS DEMO:") for item in observations)

        insight = client.get("/api/development/insights/a?days=90").json()
        assert insight["synthetic_observation_count"] == 4
        assert "tidak dipakai untuk melatih model" in insight["synthetic_demo_notice"]
        assert "96 skenario mock sintetis" in insight["synthetic_demo_notice"]
        assert next(item for item in insight["insights"] if item["aspect"] == "Bahasa")["model_activity_idea"]["synthetic_training_data"] is True
        assert next(item for item in insight["insights"] if item["aspect"] == "Bahasa")["observation_count"] == 2
        client.post("/api/auth/logout")

    with TestClient(create_app(database)) as client:
        authenticate(client, "caregiver")
        assert len(client.get("/api/observations").json()["observations"]) == 9
