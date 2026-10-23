from __future__ import annotations

import base64
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app


TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)


def test_reference_catalog_is_traceable_and_meal_combinations_are_snapshotted(tmp_path, authenticate):
    database = tmp_path / "nutrition-notifications.sqlite3"
    with TestClient(create_app(database)) as client:
        authenticate(client, "caregiver")
        response = client.get("/api/meals/catalog")
        assert response.status_code == 200
        meals = {item["id"]: item for item in response.json()["meals"]}
        assert meals["seed-tkpi2020-ap001"]["energy_kcal"] == 180
        assert meals["seed-tkpi2020-ap001"]["source_url"].startswith("https://")
        assert meals["seed-tkpi2019-dp002"]["energy_kcal"] == 11.5
        assert meals["seed-tkpi2019-jr006"]["energy_kcal"] == 122
        assert meals["seed-tkpi2020-ap029"]["energy_kcal"] == 91.4

        activity = client.post("/api/activities", json={
            "child_id": "a",
            "child_name": "Ananda A",
            "category": "Makan",
            "title": "Nasi dengan sayur",
            "note": "Nasi dan bayam disajikan; respons dicatat.",
            "session": "Siang",
            "time": "12:10",
            "share_to_parent": True,
            "meal_items": [
                {"meal_id": "seed-tkpi2020-ap001", "servings": 1},
                {"meal_id": "seed-tkpi2019-dp002", "servings": 1},
            ],
        })
        assert activity.status_code == 200, activity.text
        meal_snapshot = activity.json()["activity"]["meal"]
        assert meal_snapshot["nutrition"]["energy_kcal"] == 191.5
        assert meal_snapshot["nutrition"]["protein_g"] == 3.6
        assert [item["name"] for item in meal_snapshot["items"]] == ["Nasi putih, matang", "Bayam, rebus"]
        assert activity.json()["notifications_created"] == 1

        # Later catalog edits must not rewrite the historical meal snapshot.
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE meal_catalog SET energy_kcal = 999 WHERE id = 'seed-tkpi2020-ap001'")
        stored = client.get("/api/activities").json()["activities"]
        saved_meal_record = next(item for item in stored if item["id"] == activity.json()["activity"]["id"])
        assert saved_meal_record["meal"]["nutrition"]["energy_kcal"] == 191.5

        image_data = "data:image/png;base64," + base64.b64encode(TINY_PNG).decode("ascii")
        photo_activity = client.post("/api/activities", json={
            "child_id": "a",
            "child_name": "Ananda A",
            "category": "Bermain",
            "title": "Bermain balok",
            "note": "Menyusun balok bersama pengasuh.",
            "session": "Pagi",
            "time": "09:15",
            "share_to_parent": True,
            "photo_data_url": image_data,
            "photo_consent_confirmed": True,
        })
        assert photo_activity.status_code == 200, photo_activity.text
        photo_id = photo_activity.json()["activity"]["id"]
        client.post("/api/auth/logout")
        authenticate(client, "parent")
        parent_notifications = client.get("/api/notifications").json()["notifications"]
        photo_notice = next(item for item in parent_notifications if item["category"] == "photo")
        assert photo_notice["related_activity_id"] == photo_id
        marked = client.post(f"/api/notifications/{photo_notice['id']}/read")
        assert marked.status_code == 200
        assert marked.json()["notification"]["is_read"] is True
        photo = client.get(f"/api/activities/{photo_id}/photo")
        assert photo.status_code == 200
        assert photo.json()["data_url"] == image_data


def test_chat_and_saved_reminders_notify_only_recipients_and_support_completion(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "family-notifications.sqlite3")) as client:
        authenticate(client, "caregiver")
        sent = client.post("/api/messages", json={"child_id": "a", "text": "Kegiatan pagi sudah selesai."})
        assert sent.status_code == 201, sent.text
        assert sent.json()["notifications_created"] == 1

        reminder = client.post("/api/notifications/reminders", json={
            "child_id": "a",
            "title": "Bawa botol minum",
            "body": "Mohon bawa botol berlabel pada sesi berikutnya.",
            "due_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            "audience": "family",
        })
        assert reminder.status_code == 201, reminder.text
        assert reminder.json()["recipient_count"] == 1

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        parent_items = client.get("/api/notifications").json()["notifications"]
        assert any(item["category"] == "message" for item in parent_items)
        reminder_item = next(item for item in parent_items if item["category"] == "reminder")
        completed = client.post(f"/api/notifications/{reminder_item['id']}/complete")
        assert completed.status_code == 200
        assert completed.json()["notification"]["is_completed"] is True

        reply = client.post("/api/messages", json={"child_id": "a", "text": "Baik, akan kami siapkan."})
        assert reply.status_code == 201, reply.text
        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        caregiver_items = client.get("/api/notifications").json()["notifications"]
        assert any(item["category"] == "message" and item["title"] == "Pesan baru dari keluarga" for item in caregiver_items)


def test_reminder_rejects_unlinked_family_and_naive_timestamp(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "invalid-reminder.sqlite3")) as client:
        authenticate(client, "caregiver")
        no_parent = client.post(
            "/api/notifications/reminders",
            json={
                "child_id": "not-linked",
                "title": "Pengingat",
                "body": "Isi pengingat.",
                "due_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
                "audience": "family",
            },
        )
        assert no_parent.status_code == 403
        naive_time = client.post(
            "/api/notifications/reminders",
            json={
                "child_id": "a",
                "title": "Pengingat",
                "body": "Isi pengingat.",
                "due_at": "2026-10-22T10:00:00",
                "audience": "self",
            },
        )
        assert naive_time.status_code == 422


def test_sensor_endpoint_uses_per_device_tenant_credentials_and_exposes_real_readings(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "sensor.sqlite3")) as client:
        authenticate(client, "admin")
        registration = client.post(
            "/api/sensors/devices",
            json={"device_id": "room-sensor-01", "room_id": "Ruang Melati"},
        )
        assert registration.status_code == 201, registration.text
        sensor_key = registration.json()["sensor_key"]
        assert sensor_key

        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        assert client.get("/api/sensors/summary").json()["connected"] is False
        unauthorized = client.post(
            "/api/sensors/readings",
            headers={"X-Sensor-Key": "wrong"},
            json={"device_id": "room-sensor-01", "room_id": "Ruang Melati", "temperature_c": 25.4, "humidity_pct": 61.2},
        )
        assert unauthorized.status_code == 401
        created = client.post(
            "/api/sensors/readings",
            headers={"X-Sensor-Key": sensor_key},
            json={"device_id": "room-sensor-01", "room_id": "Ruang Melati", "temperature_c": 25.4, "humidity_pct": 61.2},
        )
        assert created.status_code == 201, created.text
        summary = client.get("/api/sensors/summary").json()
        assert summary["connected"] is True
        assert summary["fresh"] is True
        assert summary["latest"]["temperature_c"] == 25.4
        assert summary["latest"]["humidity_pct"] == 61.2
        assert summary["latest"]["room_id"] == "Ruang Melati"

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        assert client.get("/api/sensors/summary").status_code == 403
