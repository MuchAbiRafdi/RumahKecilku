from __future__ import annotations

import os

import pytest

# API tests use only the documented synthetic preview identities.
os.environ["RUMAH_APP_ENV"] = "preview"
os.environ["RUMAH_DEMO_MODE"] = "1"
os.environ.pop("RUMAH_DEMO_SAMPLE_DATA", None)
os.environ.pop("RUMAH_BROWSER_SESSION_TOKEN", None)


ROLE_EMAILS = {
    "caregiver": "pengasuh@rumahkecilku.demo",
    "doctor": "dokter@rumahkecilku.demo",
    "admin": "admin@rumahkecilku.demo",
    "parent": "orangtua@rumahkecilku.demo",
}
DEMO_PASSWORD = "RK-Preview-2026!"


@pytest.fixture
def authenticate():
    def login(client, role: str = "doctor"):
        response = client.post(
            "/api/auth/login",
            json={"email": ROLE_EMAILS[role], "password": DEMO_PASSWORD},
        )
        assert response.status_code == 200, response.text
        return response.json()["user"]

    return login
