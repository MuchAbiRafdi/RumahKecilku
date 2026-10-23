from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.main import create_app
from app.repositories.auth_repository import AuthRepository


DEMO_PASSWORD = "RK-Preview-2026!"


def _login(client: TestClient, email: str, password: str = DEMO_PASSWORD) -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _create_second_daycare(client: TestClient) -> tuple[str, str, str, str, str]:
    auth = client.app.state.auth_repository
    organization = auth.create_organization("Daycare Uji Kedua", "daycare-uji-kedua")
    user = auth.create_user(
        "Staf Tenant Kedua",
        "staf-tenant-kedua@example.test",
        "caregiver",
        hash_password("sandi-uji-tenant-kedua-26"),
    )
    auth.add_organization_member(organization["id"], user["id"], "caregiver")
    doctor = auth.create_user(
        "Dokter Tenant Kedua",
        "dokter-tenant-kedua@example.test",
        "doctor",
        hash_password("sandi-dokter-tenant-kedua-26"),
    )
    auth.add_organization_member(organization["id"], doctor["id"], "doctor")
    admin = auth.create_user(
        "Admin Tenant Kedua",
        "admin-tenant-kedua@example.test",
        "admin",
        hash_password("sandi-admin-tenant-kedua-26"),
    )
    auth.add_organization_member(organization["id"], admin["id"], "admin")
    child = auth.create_child_profile(
        organization["id"],
        "Anak Tenant Kedua",
        "2024-03-01",
        "Ruang Uji",
    )
    return organization["id"], user["email"], doctor["email"], admin["email"], child["id"]


def test_tenant_scopes_cover_children_activities_attendance_messages_and_catalog(tmp_path):
    with TestClient(create_app(tmp_path / "tenant-isolation.sqlite3")) as client:
        organization_b, email_b, doctor_email_b, admin_email_b, child_b = _create_second_daycare(client)
        user_b = _login(client, email_b, "sandi-uji-tenant-kedua-26")
        assert user_b["child_ids"] == [child_b]
        assert user_b["organization_ids"] == [organization_b]

        attendance = client.post("/api/attendance", json={"child_id": child_b, "status": "Hadir"})
        assert attendance.status_code == 200, attendance.text
        activity = client.post("/api/activities", json={
            "child_id": child_b,
            "child_name": "Anak Tenant Kedua",
            "category": "Bermain",
            "title": "Kegiatan tenant kedua",
            "note": "Catatan sintetik untuk uji isolasi.",
            "session": "Pagi",
            "time": "09:30",
            "share_to_parent": False,
        })
        assert activity.status_code == 200, activity.text

        client.post("/api/auth/logout")
        _login(client, doctor_email_b, "sandi-dokter-tenant-kedua-26")
        meal = client.post("/api/meals/catalog", json={
            "name": "Menu privat tenant kedua",
            "serving_label": "50 g",
            "serving_grams": 50,
            "energy_kcal": 50,
            "protein_g": 2,
            "carbohydrate_g": 8,
            "fat_g": 1,
            "fiber_g": 1,
            "allergens": "",
            "notes": "Nilai sintetik khusus tes, bukan data gizi untuk penggunaan nyata.",
            "source": "Sumber uji sintetis",
            "source_url": "",
        })
        assert meal.status_code == 201, meal.text

        client.post("/api/auth/logout")
        _login(client, admin_email_b, "sandi-admin-tenant-kedua-26")
        pickup_b = client.post(f"/api/attendance/children/{child_b}/authorized-pickups", json={
            "name": "Penjemput Tenant B",
            "relationship": "Keluarga",
            "parent_confirmation_method": "phone",
            "parent_confirmation_recorded": True,
        })
        assert pickup_b.status_code == 201, pickup_b.text
        pickup_b_id = pickup_b.json()["authorized_pickup"]["id"]
        device_b = client.post("/api/sensors/devices", json={"device_id": "sensor-tenant-b", "room_id": "Ruang Uji"})
        assert device_b.status_code == 201, device_b.text
        reading_payload_b = {"device_id": "sensor-tenant-b", "room_id": "Ruang Uji", "temperature_c": 26.1, "humidity_pct": 58.0}
        assert client.post("/api/sensors/readings", headers={"X-Sensor-Key": device_b.json()["sensor_key"]}, json=reading_payload_b).status_code == 201

        client.post("/api/auth/logout")
        _login(client, "admin@rumahkecilku.demo")
        assert client.get(f"/api/attendance/children/{child_b}/authorized-pickups").status_code == 403
        assert client.post(f"/api/attendance/children/{child_b}/authorized-pickups/{pickup_b_id}/revoke").status_code == 403
        assert client.post("/api/attendance/check-in", json={"child_id": child_b}).status_code == 403
        assert client.get("/api/attendance/events", params={"child_id": child_b}).status_code == 403
        device_a = client.post("/api/sensors/devices", json={"device_id": "sensor-tenant-a", "room_id": "Ruang Melati"})
        assert device_a.status_code == 201, device_a.text
        reading_payload_a = {"device_id": "sensor-tenant-a", "room_id": "Ruang Melati", "temperature_c": 24.8, "humidity_pct": 62.0}
        assert client.post("/api/sensors/readings", headers={"X-Sensor-Key": device_a.json()["sensor_key"]}, json=reading_payload_a).status_code == 201

        client.post("/api/auth/logout")
        user_a = _login(client, "pengasuh@rumahkecilku.demo")
        assert child_b not in user_a["child_ids"]
        assert organization_b not in user_a["organization_ids"]
        assert child_b not in {item["id"] for item in client.get("/api/children").json()["children"]}
        assert child_b not in {item["child_id"] for item in client.get("/api/attendance").json()["attendance"]}
        assert client.post("/api/attendance", json={"child_id": child_b, "status": "Izin"}).status_code == 403
        assert client.get(f"/api/attendance/children/{child_b}/authorized-pickups").status_code == 403
        assert client.post("/api/attendance/check-in", json={"child_id": child_b}).status_code == 403
        assert client.post("/api/attendance/check-out", json={"child_id": child_b, "pickup_authorization_id": pickup_b_id, "pickup_name_match_confirmed": True}).status_code == 403
        assert child_b not in {item["child_id"] for item in client.get("/api/activities").json()["activities"]}
        assert client.get("/api/sensors/summary").json()["latest"]["device_id"] == "sensor-tenant-a"
        assert client.post("/api/activities", json={
            "child_id": child_b,
            "child_name": "Anak Tenant Kedua",
            "category": "Bermain",
            "title": "Upaya lintas tenant",
            "note": "Harus ditolak.",
            "session": "Pagi",
            "time": "10:00",
            "share_to_parent": False,
        }).status_code == 403
        assert client.get("/api/messages/contacts", params={"child_id": child_b}).status_code == 403
        meal_names = {item["name"] for item in client.get("/api/meals/catalog").json()["meals"]}
        assert "Menu privat tenant kedua" not in meal_names
        assert client.get(f"/api/kpsp/children/{child_b}/assessments").status_code == 403

        client.post("/api/auth/logout")
        _login(client, email_b, "sandi-uji-tenant-kedua-26")
        assert child_b in {item["child_id"] for item in client.get("/api/attendance").json()["attendance"]}
        tenant_b_pickups = client.get(f"/api/attendance/children/{child_b}/authorized-pickups")
        assert tenant_b_pickups.status_code == 200
        assert [item["name"] for item in tenant_b_pickups.json()["authorized_pickups"]] == ["Penjemput Tenant B"]
        assert "Menu privat tenant kedua" in {item["name"] for item in client.get("/api/meals/catalog").json()["meals"]}
        assert client.get("/api/sensors/summary").json()["latest"]["device_id"] == "sensor-tenant-b"


def test_admin_is_operational_and_has_no_default_clinical_or_kpsp_access(tmp_path):
    with TestClient(create_app(tmp_path / "admin-scope.sqlite3")) as client:
        admin = _login(client, "admin@rumahkecilku.demo")
        assert admin["role"] == "admin"
        assert len(admin["child_ids"]) == 5
        assert len(admin["organization_ids"]) == 1

        assert client.get("/api/children").status_code == 200
        assert client.get("/api/attendance").status_code == 200
        assert client.get("/api/meals/catalog").status_code == 200
        assert client.get("/api/activities").status_code == 403
        assert client.get("/api/observations").status_code == 403
        assert client.get("/api/development/insights/a").status_code == 403
        assert client.get("/api/kpsp/schedules").status_code == 403
        assert client.get("/api/kpsp/children/a/assessments").status_code == 403

        created = client.post("/api/children", json={
            "name": "Anak Operasional Baru",
            "birth_date": "2024-01-01",
            "room": "Ruang Kenanga",
        })
        assert created.status_code == 201, created.text
        new_child_id = created.json()["child"]["id"]
        assert new_child_id in {item["id"] for item in client.get("/api/children").json()["children"]}


def test_existing_user_data_survives_admin_role_schema_migration(tmp_path):
    database = tmp_path / "legacy-auth.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TABLE auth_users (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            role TEXT NOT NULL CHECK(role IN ('parent','caregiver','doctor')),
            password_hash TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        connection.execute("""CREATE TABLE auth_sessions (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE
        )""")
        connection.execute("""CREATE TABLE auth_user_children (
            user_id TEXT NOT NULL, child_id TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(user_id, child_id), FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE
        )""")
        connection.execute(
            "INSERT INTO auth_users VALUES ('existing-user', 'Nama Lama', 'lama@example.test', 'parent', 'hash-lama', '2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO auth_user_children VALUES ('existing-user', 'legacy-child', '2026-01-01T00:00:00+00:00')"
        )

    repository = AuthRepository(database)
    repository.initialize(include_demo_accounts=False)
    existing = repository.get_by_email("lama@example.test")
    assert existing["id"] == "existing-user"
    assert existing["password_hash"] == "hash-lama"
    assert existing["child_ids"] == []  # Legacy links fail closed until explicitly migrated to a tenant.
    admin = repository.create_user("Admin Baru", "admin@example.test", "admin", hash_password("sandi-admin-aman-26"))
    assert admin["role"] == "admin"
