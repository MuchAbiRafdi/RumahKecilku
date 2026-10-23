from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies import require_roles
from app.models.schemas import ChildProfileCreate, ChildProfileUpdate, GuardianLinkAccept, GuardianLinkCreate


router = APIRouter(prefix="/children", tags=["Profil anak"])


@router.get("/links")
def list_child_links(
    request: Request,
    user: dict = Depends(require_roles("caregiver", "doctor", "admin")),
) -> dict:
    # The server derives this list from active organization membership; the browser
    # never supplies or expands the staff member's child scope.
    return {
        "child_ids": user.get("child_ids", []),
        "family_child_ids": request.app.state.auth_repository.get_children_with_linked_parent_ids(),
    }


@router.get("")
def list_children(
    request: Request,
    user: dict = Depends(require_roles("caregiver", "doctor", "admin", "parent")),
) -> dict:
    return {"children": request.app.state.auth_repository.list_child_profiles(user["id"], user["role"])}


@router.post("", status_code=201)
def create_child(
    payload: ChildProfileCreate,
    request: Request,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    organization_ids = user.get("organization_ids", [])
    organization_id = payload.organization_id
    if organization_id is None:
        if len(organization_ids) != 1:
            raise HTTPException(status_code=422, detail="Pilih daycare yang menjadi pemilik profil anak.")
        organization_id = organization_ids[0]
    if organization_id not in organization_ids:
        raise HTTPException(status_code=403, detail="Akun admin ini tidak memiliki akses ke daycare tersebut.")
    profile = request.app.state.auth_repository.create_child_profile(
        organization_id,
        payload.name,
        payload.birth_date.isoformat() if payload.birth_date else None,
        payload.room,
    )
    return {"child": profile}


@router.patch("/{child_id}")
def update_child(
    child_id: str,
    payload: ChildProfileUpdate,
    request: Request,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    if child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun admin ini tidak memiliki akses ke profil anak tersebut.")
    updates = payload.model_dump(exclude_unset=True)
    if "birth_date" in updates and updates["birth_date"] is not None:
        updates["birth_date"] = updates["birth_date"].isoformat()
    profile = request.app.state.auth_repository.update_child_profile(
        child_id=child_id,
        admin_user_id=user["id"],
        organization_ids=user.get("organization_ids", []),
        updates=updates,
    )
    if profile is None:
        raise HTTPException(status_code=403, detail="Akun admin ini tidak memiliki akses ke profil anak tersebut.")
    return {"child": profile}


@router.get("/{child_id}/profile-audit")
def list_child_profile_audit(
    child_id: str,
    request: Request,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    if child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun admin ini tidak memiliki akses ke profil anak tersebut.")
    events = request.app.state.auth_repository.list_child_profile_audit(
        child_id=child_id,
        admin_user_id=user["id"],
        organization_ids=user.get("organization_ids", []),
    )
    return {"events": events}


@router.get("/guardian-invitations")
def list_guardian_invitations(
    request: Request,
    user: dict = Depends(require_roles("parent")),
) -> dict:
    invitations = request.app.state.auth_repository.list_pending_guardian_invitations(user["id"])
    return {"invitations": invitations}


@router.get("/{child_id}/guardian-candidates")
def list_guardian_candidates(
    child_id: str,
    request: Request,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    repository = request.app.state.auth_repository
    if child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun admin ini tidak memiliki akses ke profil anak tersebut.")
    candidates = repository.list_guardian_candidates(child_id, user["id"], user.get("organization_ids", []))
    return {"candidates": candidates}


@router.get("/{child_id}/guardians")
def list_guardians(
    child_id: str,
    request: Request,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    repository = request.app.state.auth_repository
    if child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun admin ini tidak memiliki akses ke profil anak tersebut.")
    guardians = repository.list_guardian_links(child_id, user["id"], user.get("organization_ids", []))
    return {"guardians": guardians}


@router.get("/{child_id}/guardian-links/audit")
def list_guardian_link_audit(
    child_id: str,
    request: Request,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    repository = request.app.state.auth_repository
    if child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun admin ini tidak memiliki akses ke profil anak tersebut.")
    events = repository.list_guardian_link_audit(child_id, user["id"], user.get("organization_ids", []))
    return {"events": events}


@router.post("/{child_id}/guardians", status_code=201)
def create_guardian_invitation(
    child_id: str,
    payload: GuardianLinkCreate,
    request: Request,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    repository = request.app.state.auth_repository
    if child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun admin ini tidak memiliki akses ke profil anak tersebut.")
    try:
        link = repository.create_guardian_invitation(
            child_id=child_id,
            parent_user_id=payload.parent_user_id,
            admin_user_id=user["id"],
            organization_ids=user.get("organization_ids", []),
            relationship=payload.relationship,
            verification_method=payload.verification_method,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"guardian_link": link}


@router.post("/{child_id}/guardians/{parent_user_id}/revoke")
def revoke_guardian_link(
    child_id: str,
    parent_user_id: str,
    request: Request,
    user: dict = Depends(require_roles("admin")),
) -> dict:
    repository = request.app.state.auth_repository
    if child_id not in user.get("child_ids", []):
        raise HTTPException(status_code=403, detail="Akun admin ini tidak memiliki akses ke profil anak tersebut.")
    try:
        link = repository.revoke_guardian_link(
            child_id=child_id,
            parent_user_id=parent_user_id,
            admin_user_id=user["id"],
            organization_ids=user.get("organization_ids", []),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if link is None:
        raise HTTPException(status_code=404, detail="Tautan wali yang masih aktif tidak ditemukan.")
    return {"guardian_link": link}


@router.post("/{child_id}/guardian-invitations/accept")
def accept_guardian_invitation(
    child_id: str,
    payload: GuardianLinkAccept,
    request: Request,
    user: dict = Depends(require_roles("parent")),
) -> dict:
    link = request.app.state.auth_repository.decide_guardian_invitation(
        parent_user_id=user["id"], child_id=child_id, accept=True
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Permintaan relasi wali tidak ditemukan atau sudah diputuskan.")
    return {"guardian_link": link}


@router.post("/{child_id}/guardian-invitations/reject")
def reject_guardian_invitation(
    child_id: str,
    request: Request,
    user: dict = Depends(require_roles("parent")),
) -> dict:
    link = request.app.state.auth_repository.decide_guardian_invitation(
        parent_user_id=user["id"], child_id=child_id, accept=False
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Permintaan relasi wali tidak ditemukan atau sudah diputuskan.")
    return {"guardian_link": link}
