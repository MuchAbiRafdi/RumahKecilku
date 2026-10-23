from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.main import create_app


def test_guardian_link_requires_institution_check_and_parent_confirmation_then_can_be_revoked(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "guardian-links.sqlite3")) as client:
        authenticate(client, "admin")
        candidates_response = client.get("/api/children/b/guardian-candidates")
        assert candidates_response.status_code == 200, candidates_response.text
        candidates = candidates_response.json()["candidates"]
        assert len(candidates) == 1
        parent_id = candidates[0]["id"]
        assert candidates[0]["email_hint"] != "orangtua@rumahkecilku.demo"
        assert "@rumahkecilku.demo" in candidates[0]["email_hint"]

        request = {
            "parent_user_id": parent_id,
            "relationship": "  Ibu   / Wali ",
            "verification_method": "in_person",
            "institution_check_confirmed": True,
        }
        rejected_without_institution_check = client.post(
            "/api/children/b/guardians", json={**request, "institution_check_confirmed": False}
        )
        assert rejected_without_institution_check.status_code == 422
        invited = client.post("/api/children/b/guardians", json=request)
        assert invited.status_code == 201, invited.text
        link = invited.json()["guardian_link"]
        assert link["status"] == "pending"
        assert link["relationship"] == "Ibu / Wali"
        assert client.post("/api/children/b/guardians", json=request).status_code == 409
        admin_links = client.get("/api/children/b/guardians").json()["guardians"]
        assert any(item["status"] == "pending" for item in admin_links)
        assert not any(item["id"] == parent_id for item in client.get("/api/children/b/guardian-candidates").json()["candidates"])

        client.post("/api/auth/logout")
        parent = authenticate(client, "parent")
        assert parent["child_ids"] == ["a"]
        assert {item["id"] for item in client.get("/api/children").json()["children"]} == {"a"}
        invitations = client.get("/api/children/guardian-invitations").json()["invitations"]
        assert len(invitations) == 1
        assert invitations[0]["child_id"] == "b"
        assert invitations[0]["child_name"] == "Ananda B"
        assert "birth_date" not in invitations[0]
        assert client.get("/api/messages/contacts", params={"child_id": "b"}).status_code == 403
        assert client.post(
            "/api/children/b/guardian-invitations/accept", json={"confirm_relationship": False}
        ).status_code == 422

        accepted = client.post(
            "/api/children/b/guardian-invitations/accept", json={"confirm_relationship": True}
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["guardian_link"]["status"] == "verified"
        assert {item["id"] for item in client.get("/api/children").json()["children"]} == {"a", "b"}
        assert client.get("/api/messages/contacts", params={"child_id": "b"}).status_code == 200
        assert client.get("/api/children/guardian-invitations").json()["invitations"] == []

        client.post("/api/auth/logout")
        authenticate(client, "admin")
        audit = client.get("/api/children/b/guardian-links/audit").json()["events"]
        assert [item["action"] for item in audit[:2]] == ["confirmed", "requested"]
        revoked = client.post(f"/api/children/b/guardians/{parent_id}/revoke", json={})
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["guardian_link"]["status"] == "revoked"
        assert any(item["status"] == "revoked" for item in client.get("/api/children/b/guardians").json()["guardians"])

        client.post("/api/auth/logout")
        parent_after_revocation = authenticate(client, "parent")
        assert parent_after_revocation["child_ids"] == ["a"]
        assert {item["id"] for item in client.get("/api/children").json()["children"]} == {"a"}
        assert client.get("/api/messages/contacts", params={"child_id": "b"}).status_code == 403


def test_guardian_links_are_tenant_scoped_and_admin_only(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "guardian-tenant-scope.sqlite3")) as client:
        repository = client.app.state.auth_repository
        organization = repository.create_organization("Daycare Wali Kedua", "daycare-wali-kedua")
        parent = repository.create_user(
            "Keluarga Tenant Kedua", "wali-kedua@example.test", "parent", hash_password("sandi-wali-kedua-26")
        )
        repository.add_organization_member(organization["id"], parent["id"], "parent")
        child = repository.create_child_profile(organization["id"], "Ananda Tenant Kedua", "2024-01-01", "Ruang Uji")

        authenticate(client, "admin")
        assert client.get(f"/api/children/{child['id']}/guardian-candidates").status_code == 403
        assert client.get(f"/api/children/{child['id']}/guardians").status_code == 403
        assert client.patch(f"/api/children/{child['id']}", json={"room": "Tidak boleh"}).status_code == 403
        assert client.get(f"/api/children/{child['id']}/profile-audit").status_code == 403
        assert client.post(
            f"/api/children/{child['id']}/guardians",
            json={"parent_user_id": parent["id"], "relationship": "Wali", "verification_method": "in_person", "institution_check_confirmed": True},
        ).status_code == 403
        assert client.get("/api/children/a/guardian-candidates").status_code == 200

        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        assert client.get("/api/children/a/guardians").status_code == 403
        assert client.post(
            "/api/children/b/guardians",
            json={"parent_user_id": parent["id"], "relationship": "Wali", "verification_method": "in_person", "institution_check_confirmed": True},
        ).status_code == 403


def test_admin_can_update_only_basic_profile_fields_within_its_tenant(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "child-profile-update.sqlite3")) as client:
        authenticate(client, "admin")
        updated = client.patch("/api/children/a", json={
            "name": "  Ananda   Baru ",
            "birth_date": "2024-10-10",
            "room": "  Ruang Melati  ",
        })
        assert updated.status_code == 200, updated.text
        assert updated.json()["child"]["name"] == "Ananda Baru"
        assert updated.json()["child"]["birth_date"] == "2024-10-10"
        assert updated.json()["child"]["room"] == "Ruang Melati"
        audit = client.get("/api/children/a/profile-audit")
        assert audit.status_code == 200, audit.text
        assert audit.json()["events"][0]["changed_fields"] == ["birth_date", "name", "room"]
        assert "Ananda Baru" not in str(audit.json()), "audit records field names, not sensitive values"
        assert client.patch("/api/children/a", json={}).status_code == 422
        assert client.patch("/api/children/a", json={"name": None}).status_code == 422
        assert client.patch("/api/children/a", json={"birth_date": "2999-01-01"}).status_code == 422
        assert client.patch("/api/children/a", json={"allergy_notes": "tidak boleh masuk roster admin"}).status_code == 422

        client.post("/api/auth/logout")
        authenticate(client, "caregiver")
        assert client.patch("/api/children/a", json={"room": "Ruang Uji"}).status_code == 403
        assert client.get("/api/children/a/profile-audit").status_code == 403


def test_demo_seed_does_not_reactivate_a_revoked_guardian_link_on_restart(tmp_path, authenticate):
    database = tmp_path / "guardian-revoke-persists.sqlite3"
    with TestClient(create_app(database)) as client:
        authenticate(client, "admin")
        link = client.get("/api/children/a/guardians").json()["guardians"][0]
        assert link["status"] == "verified"
        revoked = client.post(f"/api/children/a/guardians/{link['parent_user_id']}/revoke", json={})
        assert revoked.status_code == 200, revoked.text
        client.post("/api/auth/logout")
        authenticate(client, "parent")
        assert client.get("/api/children").json()["children"] == []

    with TestClient(create_app(database)) as client:
        authenticate(client, "parent")
        assert client.get("/api/children").json()["children"] == []
        client.post("/api/auth/logout")
        authenticate(client, "admin")
        assert client.get("/api/children/a/guardians").json()["guardians"][0]["status"] == "revoked"


def test_parent_can_decline_pending_guardian_link_without_receiving_child_access(tmp_path, authenticate):
    with TestClient(create_app(tmp_path / "guardian-reject.sqlite3")) as client:
        authenticate(client, "admin")
        candidate = client.get("/api/children/c/guardian-candidates").json()["candidates"][0]
        response = client.post("/api/children/c/guardians", json={
            "parent_user_id": candidate["id"],
            "relationship": "Wali",
            "verification_method": "institution_record",
            "institution_check_confirmed": True,
        })
        assert response.status_code == 201, response.text

        client.post("/api/auth/logout")
        authenticate(client, "parent")
        declined = client.post("/api/children/c/guardian-invitations/reject", json={})
        assert declined.status_code == 200, declined.text
        assert declined.json()["guardian_link"]["status"] == "rejected"
        assert "c" not in client.get("/api/auth/me").json()["user"]["child_ids"]
        assert client.get("/api/children/guardian-invitations").json()["invitations"] == []

        client.post("/api/auth/logout")
        authenticate(client, "admin")
        candidates_again = client.get("/api/children/c/guardian-candidates").json()["candidates"]
        assert candidates_again and candidates_again[0]["id"] == candidate["id"]
        assert client.post("/api/children/c/guardians", json={
            "parent_user_id": candidate["id"],
            "relationship": "Wali",
            "verification_method": "institution_record",
            "institution_check_confirmed": True,
        }).status_code == 201
        audit = client.get("/api/children/c/guardian-links/audit").json()["events"]
        assert [item["action"] for item in audit[:2]] == ["reissued", "rejected"]
