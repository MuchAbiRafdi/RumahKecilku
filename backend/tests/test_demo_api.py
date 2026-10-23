import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.main import create_app


def test_messacare_endpoint_is_a_disclosed_deterministic_demo(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "messacare.sqlite3")) as client:
        authenticate(client, "caregiver")
        response = client.post(
            "/api/ai/messacare/announcement",
            json={
                "child_name": "Ananda A",
                "category": "Stimulasi",
                "title": "Membaca dialogis",
                "note": "Bergiliran menunjuk gambar.",
                "session": "Pagi",
                "time": "10:20",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["demo"] is True
        assert payload["engine"] == "MessaCare template demo v0.1"
        assert "bukan penilaian perkembangan" in payload["text"]
        assert "Ananda A" in payload["text"]


def test_caregiver_activity_is_persisted_and_shared_through_messacare(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "activities.sqlite3")) as client:
        authenticate(client, "caregiver")
        activity_payload = {
            "child_id": "a",
            "child_name": "Ananda A",
            "category": "Stimulasi",
            "title": "Membaca dialogis",
            "note": "Bergiliran menunjuk gambar.",
            "session": "Pagi",
            "time": "10:20",
            "share_to_parent": True,
        }
        response = client.post("/api/activities", json=activity_payload)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["activity"]["shared"] is True
        assert payload["activity"]["id"].startswith("activity-")
        assert payload["announcement"]["demo"] is True
        assert "bukan penilaian perkembangan" in payload["announcement"]["text"]
        private_payload = {**activity_payload, "title": "Catatan internal", "share_to_parent": False}
        private = client.post("/api/activities", json=private_payload)
        assert private.status_code == 200
        assert private.json()["announcement"] is None
        unlinked = client.post("/api/activities", json={**activity_payload, "child_id": "b", "title": "Tidak terkirim"})
        assert unlinked.status_code == 409
        assert client.get("/api/children/links").json()["child_ids"] == ["a", "b", "c", "d", "e"]
        stored = client.get("/api/activities")
        assert stored.status_code == 200
        assert len(stored.json()["activities"]) == 2
        assert stored.json()["activities"][1]["id"] == payload["activity"]["id"]
        assert stored.json()["activities"][1]["announcement"]["text"] == payload["announcement"]["text"]
        caregiver_chat = client.get("/api/messages").json()["messages"]
        assert any(item["kind"] == "Kegiatan dibagikan" for item in caregiver_chat)
        assert any(item["kind"] == "Perubahan catatan tim tersimpan" for item in caregiver_chat)

        client.post("/api/auth/logout")
        authenticate(client, "doctor")
        doctor_chat = client.get("/api/messages").json()["messages"]
        assert any(item["kind"] == "Kegiatan dibagikan" for item in doctor_chat)
        assert any(item["kind"] == "Perubahan catatan tim tersimpan" for item in doctor_chat)
        assert all("Catatan internal" not in item["text"] for item in doctor_chat)
        doctor_notifications = client.get("/api/notifications").json()["notifications"]
        doctor_notice_message_ids = {item["related_message_id"] for item in doctor_notifications}
        assert {item["id"] for item in doctor_chat} <= doctor_notice_message_ids
        marked_doctor_notice = client.post(f"/api/notifications/{doctor_notifications[0]['id']}/read")
        assert marked_doctor_notice.status_code == 200
        assert marked_doctor_notice.json()["notification"]["is_read"] is True
        doctor_activities = client.get("/api/activities")
        assert doctor_activities.status_code == 200
        assert len(doctor_activities.json()["activities"]) == 2
        assert client.post("/api/activities", json=activity_payload).status_code == 403

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        parent_activities = client.get("/api/activities")
        assert parent_activities.status_code == 200
        assert len(parent_activities.json()["activities"]) == 1
        assert parent_activities.json()["activities"][0]["title"] == "Membaca dialogis"
        parent_chat = client.get("/api/messages").json()["messages"]
        assert any(item["kind"] == "Kegiatan dibagikan" for item in parent_chat)
        assert all("Catatan internal" not in item["text"] for item in parent_chat)


def test_observations_are_persisted_for_caregiver_and_doctor_only(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "observations.sqlite3")) as client:
        authenticate(client, "caregiver")
        response = client.post(
            "/api/observations",
            json={
                "child_id": "a",
                "aspect": "Bahasa",
                "reference": "",
                "result": "Teramati",
                "context": "Membaca buku bersama.",
                "note": "Anak menunjuk gambar saat diminta.",
                "time": "10:30",
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["observation"]["child_id"] == "a"
        assert len(client.get("/api/observations").json()["observations"]) == 1

        client.post("/api/auth/logout")
        authenticate(client, "doctor")
        assert len(client.get("/api/observations").json()["observations"]) == 1
        assert client.post("/api/observations", json=response.json()["observation"]).status_code == 403

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        assert client.get("/api/observations").status_code == 403
        assert client.post("/api/observations", json=response.json()["observation"]).status_code == 403


def test_attendance_is_persisted_and_filtered_for_parent_accounts(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "attendance.sqlite3")) as client:
        authenticate(client, "caregiver")
        first = client.post("/api/attendance", json={"child_id": "a", "status": "Hadir"})
        second = client.post("/api/attendance", json={"child_id": "b", "status": "Izin"})
        assert first.status_code == 200, first.text
        assert first.json()["attendance"]["check_in"] != "Belum dicatat"
        assert second.status_code == 200
        assert len(client.get("/api/attendance").json()["attendance"]) == 2

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        records = client.get("/api/attendance").json()["attendance"]
        assert len(records) == 1
        assert records[0]["child_id"] == "a"
        assert records[0]["status"] == "Hadir"
        assert client.post("/api/attendance", json={"child_id": "a", "status": "Izin"}).status_code == 403



def test_previous_day_attendance_is_not_counted_as_todays_presence(tmp_path, authenticate):
    database_path = tmp_path / "stale-attendance.sqlite3"
    with TestClient(create_app(database_path)) as client:
        authenticate(client, "caregiver")
        response = client.post("/api/attendance", json={"child_id": "a", "status": "Hadir"})
        assert response.status_code == 200
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
        yesterday_local_date = (datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Jakarta")).date() - timedelta(days=1)).isoformat()
        with sqlite3.connect(database_path) as connection:
            connection.execute("UPDATE child_attendance SET updated_at = ? WHERE child_id = 'a'", (yesterday,))
            connection.execute("UPDATE attendance_sessions SET local_date = ?, updated_at = ? WHERE child_id = 'a'", (yesterday_local_date, yesterday))
        assert client.get("/api/attendance").json()["attendance"] == []


def test_family_messages_are_persisted_and_limited_to_linked_children(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "family-messages.sqlite3")) as client:
        authenticate(client, "caregiver")
        targeted = client.post("/api/messages", json={"child_id": "a", "text": "Kabar untuk keluarga Ananda A."})
        assert targeted.status_code == 201, targeted.text
        announcement = client.post("/api/messages", json={"child_id": None, "text": "Pengumuman untuk keluarga tertaut."})
        assert announcement.status_code == 201, announcement.text
        unlinked = client.post("/api/messages", json={"child_id": "b", "text": "Tidak ada penerima tertaut."})
        assert unlinked.status_code == 409
        assert len(client.get("/api/messages").json()["messages"]) == 2

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        me = client.get("/api/auth/me").json()["user"]
        assert me["child_ids"] == ["a"]
        parent_messages = client.get("/api/messages")
        assert parent_messages.status_code == 200
        assert {item["text"] for item in parent_messages.json()["messages"]} == {
            "Kabar untuk keluarga Ananda A.",
            "Pengumuman untuk keluarga tertaut.",
        }
        reply = client.post("/api/messages", json={"child_id": "a", "text": "Terima kasih atas kabarnya."})
        assert reply.status_code == 201
        assert reply.json()["message"]["kind"] == "Balasan"
        assert client.post("/api/messages", json={"child_id": "b", "text": "Pesan salah profil."}).status_code == 403
        assert client.post("/api/messages", json={"child_id": None, "text": "Pesan tanpa profil."}).status_code == 403
        assert len(client.get("/api/messages").json()["messages"]) == 3

        client.post("/api/auth/logout")
        authenticate(client, "doctor")
        assert client.get("/api/children/links").json()["child_ids"] == ["a", "b", "c", "d", "e"]
        doctor_messages = client.get("/api/messages")
        assert doctor_messages.status_code == 200
        assert doctor_messages.json()["messages"] == []  # Legacy family announcements are not a doctor thread.
        assert client.post("/api/messages", json={"child_id": "a", "text": "Pesan dokter tanpa penerima."}).status_code == 422
        contacts = client.get("/api/messages/contacts", params={"child_id": "a"})
        assert contacts.status_code == 200
        parent_contact = next(item for item in contacts.json()["contacts"] if item["role"] == "parent")
        direct = client.post("/api/messages", json={
            "child_id": "a",
            "recipient_id": parent_contact["id"],
            "text": "Dokter membagikan ringkasan yang sudah ditinjau.",
        })
        assert direct.status_code == 201, direct.text
        assert direct.json()["message"]["is_direct"] is True
        assert direct.json()["message"]["recipient_id"] == parent_contact["id"]
        assert direct.json()["notifications_created"] == 1
        assert len(client.get("/api/messages").json()["messages"]) == 1

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        parent_after_doctor_message = client.get("/api/messages").json()["messages"]
        assert any(item["text"] == "Dokter membagikan ringkasan yang sudah ditinjau." for item in parent_after_doctor_message)
        assert any(item["category"] == "message" for item in client.get("/api/notifications").json()["notifications"])


def test_model_status_discloses_synthetic_activity_demo_and_no_clinical_validation(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "model-status.sqlite3")) as client:
        authenticate(client, "doctor")
        response = client.get("/api/development/model-status")
        assert response.status_code == 200
        payload = response.json()
        assert payload["available"] is True
        assert payload["ml_trained"] is True
        assert payload["demo_activity_model_available"] is True
        assert payload["clinical_model_available"] is False
        assert payload["clinical_validated"] is False
        assert payload["training_data_synthetic"] is True
        assert payload["ml_demo_training_examples"] == 96
        assert payload["external_ai_api"] is False
        assert payload["demo_values_must_not_be_used_clinically"] is True


def test_root_and_health_endpoints_are_available(tmp_path):
    with TestClient(create_app(tmp_path / "health.sqlite3")) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/health").json()["status"] == "ok"


def test_authentication_registers_sessions_and_gates_roles(tmp_path):
    with TestClient(create_app(tmp_path / "auth.sqlite3")) as client:
        assert client.get("/api/auth/me").json()["user"] is None
        assert client.get("/api/kpsp/schedules").status_code == 401
        registration = client.post(
            "/api/auth/register",
            json={
                "name": "Keluarga Baru",
                "email": " keluarga@example.test ",
                "password": "kata-sandi-aman-26",
                "role": "parent",
            },
        )
        assert registration.status_code == 201, registration.text
        assert registration.json()["user"]["role"] == "parent"
        assert client.get("/api/auth/me").json()["user"]["email"] == "keluarga@example.test"
        assert client.get("/api/kpsp/schedules").status_code == 403

        client.post("/api/auth/logout")
        assert client.get("/api/auth/me").json()["user"] is None
        login = client.post(
            "/api/auth/login",
            json={"email": "keluarga@example.test", "password": "kata-sandi-aman-26"},
        )
        assert login.status_code == 200
        assert login.json()["user"]["role"] == "parent"

        client.post("/api/auth/logout")
        doctor_login = client.post(
            "/api/auth/login",
            json={"email": "dokter@rumahkecilku.demo", "password": "RK-Preview-2026!"},
        )
        assert doctor_login.status_code == 200
        assert doctor_login.json()["user"]["role"] == "doctor"
        assert client.get("/api/kpsp/schedules").status_code == 200
        denied = client.post(
            "/api/ai/messacare/announcement",
            json={
                "child_name": "Ananda A",
                "category": "Stimulasi",
                "title": "Membaca dialogis",
                "note": "Catatan uji.",
                "session": "Pagi",
                "time": "10:20",
            },
        )
        assert denied.status_code == 403


def test_all_four_demo_accounts_can_sign_in(tmp_path):
    credentials = [
        ("pengasuh@rumahkecilku.demo", "caregiver"),
        ("dokter@rumahkecilku.demo", "doctor"),
        ("admin@rumahkecilku.demo", "admin"),
        ("orangtua@rumahkecilku.demo", "parent"),
    ]
    with TestClient(create_app(tmp_path / "all-demo-logins.sqlite3")) as client:
        for email, role in credentials:
            response = client.post(
                "/api/auth/login",
                json={"email": email, "password": "RK-Preview-2026!"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["user"]["role"] == role
            client.post("/api/auth/logout")


def test_demo_password_is_repaired_if_a_legacy_hash_is_stored(tmp_path):
    database = tmp_path / "stale-demo-account.sqlite3"
    with TestClient(create_app(database)):
        pass
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE auth_users SET password_hash = ? WHERE email = ?",
            ("legacy-hash", "dokter@rumahkecilku.demo"),
        )
    with TestClient(create_app(database)) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "dokter@rumahkecilku.demo", "password": "RK-Preview-2026!"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["user"]["role"] == "doctor"


def test_session_cookie_is_secure_for_https_preview_origin(tmp_path):
    with TestClient(create_app(tmp_path / "auth-cookie.sqlite3")) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "dokter@rumahkecilku.demo", "password": "RK-Preview-2026!"},
            headers={"origin": "https://3000-preview.example.test"},
        )
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert "secure" in cookie


def test_embedded_preview_can_use_tab_scoped_bearer_session(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMAH_BROWSER_SESSION_TOKEN", "1")
    with TestClient(create_app(tmp_path / "embedded-session.sqlite3")) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "dokter@rumahkecilku.demo", "password": "RK-Preview-2026!"},
        )
        assert login.status_code == 200
        token = login.json().get("session_token")
        assert token
        client.cookies.clear()  # Simulate a browser that blocks third-party cookies.
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/auth/me", headers=headers).json()["user"]["role"] == "doctor"
        assert client.get("/api/kpsp/schedules", headers=headers).status_code == 200

        # Some embedded preview proxies rewrite Authorization; the namespaced header must still work.
        proxy_headers = {
            "Authorization": "Bearer unrelated-proxy-value",
            "X-Rumah-Kecilku-Session": token,
        }
        assert client.get("/api/auth/me", headers=proxy_headers).json()["user"]["role"] == "doctor"
        assert client.get("/api/kpsp/schedules", headers=proxy_headers).status_code == 200
        assert client.post("/api/auth/logout", headers=proxy_headers).status_code == 200
        assert client.get("/api/kpsp/schedules", headers=proxy_headers).status_code == 401


def test_session_token_is_not_exposed_without_demo_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("RUMAH_BROWSER_SESSION_TOKEN", raising=False)
    with TestClient(create_app(tmp_path / "cookie-only-session.sqlite3")) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "pengasuh@rumahkecilku.demo", "password": "RK-Preview-2026!"},
        )
        assert login.status_code == 200
        assert "session_token" not in login.json()


def test_registration_rejects_duplicate_email_and_short_password(tmp_path):
    with TestClient(create_app(tmp_path / "auth-validation.sqlite3")) as client:
        existing = client.post(
            "/api/auth/register",
            json={
                "name": "Akun baru",
                "email": "pengasuh@rumahkecilku.demo",
                "password": "kata-sandi-aman-26",
                "role": "parent",
            },
        )
        assert existing.status_code == 409
        short_password = client.post(
            "/api/auth/register",
            json={"name": "Akun baru", "email": "baru@example.test", "password": "pendek", "role": "parent"},
        )
        assert short_password.status_code == 422
