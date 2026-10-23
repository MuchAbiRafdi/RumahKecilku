from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def _demo_credentials() -> dict[str, str]:
    return {"email": "dokter@rumahkecilku.demo", "password": "RK-Preview-2026!"}


def test_public_registration_cannot_assign_staff_roles(tmp_path):
    with TestClient(create_app(tmp_path / "staff-signup.sqlite3")) as client:
        for role in ("caregiver", "doctor"):
            response = client.post(
                "/api/auth/register",
                json={
                    "name": "Akun Tanpa Undangan",
                    "email": f"{role}@example.test",
                    "password": "kata-sandi-minimal-26",
                    "role": role,
                },
            )
            assert response.status_code == 422, response.text

        # Older clients may omit role; it is safely fixed to parent, never elevated.
        parent = client.post(
            "/api/auth/register",
            json={
                "name": "Orang Tua Baru",
                "email": "parent-new@example.test",
                "password": "kata-sandi-minimal-26",
            },
        )
        assert parent.status_code == 201, parent.text
        assert parent.json()["user"]["role"] == "parent"


def test_demo_accounts_are_not_seeded_or_usable_outside_preview(tmp_path, monkeypatch):
    database = tmp_path / "no-demo.sqlite3"
    monkeypatch.setenv("RUMAH_APP_ENV", "development")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "0")
    monkeypatch.delenv("RUMAH_BROWSER_SESSION_TOKEN", raising=False)

    with TestClient(create_app(database)) as client:
        response = client.post("/api/auth/login", json=_demo_credentials())
        assert response.status_code == 401
        with sqlite3.connect(database) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM auth_users WHERE email LIKE '%@rumahkecilku.demo'"
            ).fetchone()[0]
        assert count == 0


def test_existing_demo_identity_is_denied_when_demo_mode_is_off(tmp_path, monkeypatch):
    database = tmp_path / "legacy-demo.sqlite3"
    monkeypatch.setenv("RUMAH_APP_ENV", "preview")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "1")
    monkeypatch.delenv("RUMAH_BROWSER_SESSION_TOKEN", raising=False)
    with TestClient(create_app(database)):
        pass

    monkeypatch.setenv("RUMAH_APP_ENV", "development")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "0")
    with TestClient(create_app(database)) as client:
        response = client.post("/api/auth/login", json=_demo_credentials())
        assert response.status_code == 401


def test_existing_demo_cookie_session_is_denied_when_demo_mode_is_off(tmp_path, monkeypatch):
    database = tmp_path / "legacy-demo-session.sqlite3"
    monkeypatch.setenv("RUMAH_APP_ENV", "preview")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "1")
    monkeypatch.delenv("RUMAH_BROWSER_SESSION_TOKEN", raising=False)
    with TestClient(create_app(database)) as preview_client:
        login = preview_client.post("/api/auth/login", json=_demo_credentials())
        assert login.status_code == 200
        cookie = preview_client.cookies.get("rumah_kecilku_session")
        assert cookie

    monkeypatch.setenv("RUMAH_APP_ENV", "development")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "0")
    with TestClient(create_app(database)) as normal_client:
        normal_client.cookies.set("rumah_kecilku_session", cookie)
        assert normal_client.get("/api/auth/me").json()["user"] is None
        assert normal_client.get("/api/kpsp/schedules").status_code == 401


def test_browser_bearer_session_is_ignored_outside_synthetic_preview(tmp_path, monkeypatch):
    database = tmp_path / "preview-token.sqlite3"
    monkeypatch.setenv("RUMAH_APP_ENV", "preview")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "1")
    monkeypatch.setenv("RUMAH_BROWSER_SESSION_TOKEN", "1")
    with TestClient(create_app(database)) as client:
        login = client.post("/api/auth/login", json=_demo_credentials())
        token = login.json().get("session_token")
        assert login.status_code == 200 and token

    monkeypatch.setenv("RUMAH_APP_ENV", "development")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "0")
    monkeypatch.setenv("RUMAH_BROWSER_SESSION_TOKEN", "0")
    with TestClient(create_app(database)) as client:
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.json()["user"] is None
        assert client.get(
            "/api/kpsp/schedules", headers={"X-Rumah-Kecilku-Session": token}
        ).status_code == 401


def test_production_startup_fails_closed_until_blockers_are_resolved(monkeypatch):
    monkeypatch.setenv("RUMAH_APP_ENV", "production")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "0")
    monkeypatch.setenv("RUMAH_BROWSER_SESSION_TOKEN", "0")
    with pytest.raises(RuntimeError, match="Startup produksi ditolak"):
        create_app()


def test_browser_token_flag_requires_demo_preview(monkeypatch):
    monkeypatch.setenv("RUMAH_APP_ENV", "development")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "1")
    monkeypatch.setenv("RUMAH_BROWSER_SESSION_TOKEN", "1")
    with pytest.raises(RuntimeError, match="hanya boleh diaktifkan"):
        create_app()


def test_synthetic_sample_seed_requires_explicit_demo_preview(monkeypatch):
    monkeypatch.setenv("RUMAH_APP_ENV", "preview")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "0")
    monkeypatch.setenv("RUMAH_DEMO_SAMPLE_DATA", "1")
    monkeypatch.delenv("RUMAH_BROWSER_SESSION_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="Data observasi sintetis hanya boleh diaktifkan"):
        create_app()


def test_synthetic_sample_seed_cannot_use_default_persistent_database(monkeypatch):
    monkeypatch.setenv("RUMAH_APP_ENV", "preview")
    monkeypatch.setenv("RUMAH_DEMO_MODE", "1")
    monkeypatch.setenv("RUMAH_DEMO_SAMPLE_DATA", "1")
    monkeypatch.delenv("RUMAH_DB_PATH", raising=False)
    monkeypatch.delenv("RUMAH_BROWSER_SESSION_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="RUMAH_DB_PATH eksplisit"):
        create_app()


def test_login_is_throttled_after_ten_failures_and_success_clears_counter(tmp_path):
    with TestClient(create_app(tmp_path / "login-throttle.sqlite3")) as client:
        invalid = {"email": "missing-user@example.test", "password": "wrong-password"}
        for _ in range(10):
            assert client.post("/api/auth/login", json=invalid).status_code == 401
        limited = client.post("/api/auth/login", json=invalid)
        assert limited.status_code == 429
        assert limited.headers["retry-after"] == "900"

        # A successful login clears that account's failure window.
        good = client.post("/api/auth/login", json=_demo_credentials())
        assert good.status_code == 200
        bad_after_success = client.post(
            "/api/auth/login",
            json={"email": "dokter@rumahkecilku.demo", "password": "wrong-password"},
        )
        assert bad_after_success.status_code == 401


def test_sensitive_api_responses_have_no_store_and_security_headers(tmp_path):
    with TestClient(create_app(tmp_path / "headers.sqlite3")) as client:
        response = client.get("/api/auth/me")
        assert response.headers["cache-control"] == "no-store, max-age=0"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_untrusted_host_is_rejected_with_security_headers(tmp_path):
    with TestClient(create_app(tmp_path / "host-check.sqlite3")) as client:
        response = client.get("/api/health", headers={"Host": "attacker.invalid"})
        assert response.status_code == 400
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store, max-age=0"


def test_oversized_request_is_rejected_with_security_headers(tmp_path):
    with TestClient(create_app(tmp_path / "body-limit.sqlite3")) as client:
        response = client.post(
            "/api/auth/login",
            content=b"",
            headers={"Content-Length": str(5 * 1024 * 1024 + 1), "Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store, max-age=0"


def test_database_file_permissions_are_private_on_posix(tmp_path):
    database = tmp_path / "private.sqlite3"
    with TestClient(create_app(database)):
        pass
    if Path("/").exists() and hasattr(database.stat(), "st_mode"):
        assert database.stat().st_mode & 0o777 == 0o600
