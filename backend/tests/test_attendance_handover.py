import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app


def test_authorized_pickup_check_in_and_check_out_leave_scoped_handover_trail(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "handover.sqlite3")) as client:
        authenticate(client, "admin")
        created = client.post("/api/attendance/children/a/authorized-pickups", json={
            "name": "  Budi   Santoso ",
            "relationship": "Kakek",
            "parent_confirmation_method": "in_person",
            "parent_confirmation_recorded": True,
        })
        assert created.status_code == 201, created.text
        pickup = created.json()["authorized_pickup"]
        assert pickup["name"] == "Budi Santoso"
        assert "phone" not in pickup and "identity_number" not in pickup and "document" not in pickup
        assert client.get("/api/attendance/children/a/authorized-pickups").json()["authorized_pickups"][0]["id"] == pickup["id"]

        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        check_in = client.post("/api/attendance/check-in", json={"child_id": "a"})
        assert check_in.status_code == 200, check_in.text
        assert check_in.json()["attendance"]["status"] == "Hadir"
        assert check_in.json()["attendance"]["check_in"] != "Belum dicatat"
        assert client.post("/api/attendance/check-in", json={"child_id": "a"}).status_code == 409
        assert client.post("/api/attendance", json={"child_id": "a", "status": "Izin"}).status_code == 409
        assert client.post("/api/attendance/check-out", json={
            "child_id": "a", "pickup_authorization_id": pickup["id"], "pickup_name_match_confirmed": False,
        }).status_code == 422
        checked_out = client.post("/api/attendance/check-out", json={
            "child_id": "a", "pickup_authorization_id": pickup["id"], "pickup_name_match_confirmed": True,
        })
        assert checked_out.status_code == 200, checked_out.text
        assert checked_out.json()["attendance"]["pickup_person_name"] == "Budi Santoso"
        assert checked_out.json()["attendance"]["check_out"] != "Belum dicatat"
        assert client.post("/api/attendance/check-out", json={
            "child_id": "a", "pickup_authorization_id": pickup["id"], "pickup_name_match_confirmed": True,
        }).status_code == 409

        assert client.get("/api/attendance/events", params={"child_id": "a"}).status_code == 403
        client.post("/api/auth/logout")
        authenticate(client, "admin")
        events = client.get("/api/attendance/events", params={"child_id": "a"})
        assert events.status_code == 200
        assert [event["event_type"] for event in reversed(events.json()["events"])] == [
            "authorized_pickup_added", "check_in", "check_out",
        ]
        handover = events.json()["events"][0]
        assert handover["pickup_person_name"] == "Budi Santoso"
        assert handover["pickup_name_match_confirmed"] is True
        assert handover["actor_name"]

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        parent_attendance = client.get("/api/attendance").json()["attendance"]
        assert len(parent_attendance) == 1
        assert parent_attendance[0]["child_id"] == "a"
        assert parent_attendance[0]["check_out"] != "Belum dicatat"
        assert parent_attendance[0]["pickup_person_name"] == "Budi Santoso"
        assert client.get("/api/attendance/children/a/authorized-pickups").status_code == 403
        assert client.get("/api/attendance/events", params={"child_id": "a"}).status_code == 403

        client.post("/api/auth/logout")
        authenticate(client, "doctor")
        doctor_record = next(item for item in client.get("/api/attendance").json()["attendance"] if item["child_id"] == "a")
        assert doctor_record["pickup_person_name"] is None
        assert client.get("/api/attendance/children/a/authorized-pickups").status_code == 403
        assert client.get("/api/attendance/events", params={"child_id": "a"}).status_code == 403


def test_pickup_authorization_requires_admin_recorded_parent_confirmation(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "pickup-consent.sqlite3")) as client:
        authenticate(client, "admin")
        base = {
            "name": "Rina",
            "relationship": "Bibi",
            "parent_confirmation_method": "phone",
            "parent_confirmation_recorded": False,
        }
        assert client.post("/api/attendance/children/a/authorized-pickups", json=base).status_code == 422
        assert client.post("/api/attendance/children/a/authorized-pickups", json={
            **base,
            "parent_confirmation_recorded": True,
            "identity_number": "must-not-be-stored",
        }).status_code == 422
        created = client.post("/api/attendance/children/a/authorized-pickups", json={
            **base,
            "parent_confirmation_recorded": True,
        })
        assert created.status_code == 201
        pickup_id = created.json()["authorized_pickup"]["id"]
        duplicate = client.post("/api/attendance/children/a/authorized-pickups", json={
            **base,
            "parent_confirmation_recorded": True,
        })
        assert duplicate.status_code == 409

        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        assert client.post("/api/attendance/children/a/authorized-pickups", json={
            **base,
            "parent_confirmation_recorded": True,
        }).status_code == 403
        assert client.post(f"/api/attendance/children/a/authorized-pickups/{pickup_id}/revoke").status_code == 403

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        assert client.post("/api/attendance/children/a/authorized-pickups", json={
            **base,
            "parent_confirmation_recorded": True,
        }).status_code == 403


def test_revoked_pickup_cannot_be_used_for_check_out_and_revocation_is_audited(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "pickup-revocation.sqlite3")) as client:
        authenticate(client, "admin")
        pickup = client.post("/api/attendance/children/a/authorized-pickups", json={
            "name": "Dewi Kurnia",
            "relationship": "Tante",
            "parent_confirmation_method": "offline_written_record",
            "parent_confirmation_recorded": True,
        }).json()["authorized_pickup"]
        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        assert client.post("/api/attendance/check-in", json={"child_id": "a"}).status_code == 200

        client.post("/api/auth/logout")
        authenticate(client, "admin")
        revoked = client.post(f"/api/attendance/children/a/authorized-pickups/{pickup['id']}/revoke")
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["authorized_pickup"]["status"] == "revoked"
        assert client.get("/api/attendance/children/a/authorized-pickups").json()["authorized_pickups"] == []
        assert any(event["event_type"] == "authorized_pickup_revoked" for event in client.get("/api/attendance/events", params={"child_id": "a"}).json()["events"])

        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        attempted = client.post("/api/attendance/check-out", json={
            "child_id": "a", "pickup_authorization_id": pickup["id"], "pickup_name_match_confirmed": True,
        })
        assert attempted.status_code == 404


def test_legacy_same_day_presence_is_migrated_for_safe_check_out(tmp_path, authenticate):
    database = tmp_path / "legacy-attendance-migration.sqlite3"
    with TestClient(create_app(database)) as client:
        authenticate(client, "caregiver")
        legacy = client.post("/api/attendance", json={"child_id": "a", "status": "Hadir"})
        assert legacy.status_code == 200
        with sqlite3.connect(database) as connection:
            connection.execute("DELETE FROM attendance_sessions WHERE child_id = 'a'")

    with TestClient(create_app(database)) as client:
        authenticate(client, "admin")
        pickup = client.post("/api/attendance/children/a/authorized-pickups", json={
            "name": "Sari Contoh",
            "relationship": "Bibi",
            "parent_confirmation_method": "phone",
            "parent_confirmation_recorded": True,
        }).json()["authorized_pickup"]
        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        migrated = next(item for item in client.get("/api/attendance").json()["attendance"] if item["child_id"] == "a")
        assert migrated["check_in"] != "Belum dicatat"
        handover = client.post("/api/attendance/check-out", json={
            "child_id": "a", "pickup_authorization_id": pickup["id"], "pickup_name_match_confirmed": True,
        })
        assert handover.status_code == 200, handover.text
