from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlite3 import IntegrityError

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.security import hash_password, hash_session_token, new_session_token, verify_password
from app.models.schemas import AuthLoginRequest, AuthRegisterRequest
from app.repositories.auth_repository import AuthRepository


router = APIRouter(prefix="/auth", tags=["Autentikasi"])
SESSION_COOKIE = "rumah_kecilku_session"
SESSION_HOURS = 12
LOGIN_FAILURE_LIMIT = 10
LOGIN_WINDOW_SECONDS = 15 * 60
_DUMMY_PASSWORD_HASH = hash_password("login-timing-placeholder-not-a-user")


def _repository(request: Request) -> AuthRepository:
    return request.app.state.auth_repository


def _is_secure_request(request: Request) -> bool:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip().lower()
    origin = request.headers.get("origin") or ""
    return request.url.scheme == "https" or forwarded_proto == "https" or origin.lower().startswith("https://")


def _issue_session(response: Response, request: Request, user_id: str, repository: AuthRepository) -> str:
    raw_token = new_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    repository.create_session(hash_session_token(raw_token), user_id, expires_at)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw_token,
        max_age=SESSION_HOURS * 60 * 60,
        expires=expires_at,
        httponly=True,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
    )
    return raw_token


def _authentication_response(user: dict, raw_token: str, request: Request) -> dict:
    payload = {"user": user}
    settings = request.app.state.settings
    # This fallback is intentionally restricted to the synthetic-data embedded preview.
    if settings.demo_mode and settings.browser_session_token and settings.app_env == "preview":
        payload["session_token"] = raw_token
    return payload


def _request_session_token(request: Request) -> str | None:
    settings = request.app.state.settings
    if settings.app_env == "preview" and settings.demo_mode and settings.browser_session_token:
        # Prefer the namespaced header first in case an outer preview proxy rewrites Authorization.
        preview_token = (request.headers.get("x-rumah-kecilku-session") or "").strip()
        if preview_token:
            return preview_token
        authorization = request.headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if separator and scheme.lower() == "bearer" and token.strip():
            return token.strip()
    # Outside that explicitly synthetic preview, accept only the HttpOnly session cookie.
    return request.cookies.get(SESSION_COOKIE)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: AuthRegisterRequest, request: Request, response: Response) -> dict:
    repository = _repository(request)
    if repository.get_by_email(payload.email):
        raise HTTPException(status_code=409, detail="Email ini sudah terdaftar. Silakan masuk.")
    try:
        user = repository.create_user(
            payload.name,
            payload.email,
            payload.role,
            hash_password(payload.password),
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Email ini sudah terdaftar. Silakan masuk.") from exc
    token = _issue_session(response, request, user["id"], repository)
    return _authentication_response(user, token, request)


@router.post("/login")
def login(payload: AuthLoginRequest, request: Request, response: Response) -> dict:
    repository = _repository(request)
    identity_hash = repository.hash_login_identifier(payload.email)
    if repository.is_login_throttled(
        identity_hash,
        max_attempts=LOGIN_FAILURE_LIMIT,
        window_seconds=LOGIN_WINDOW_SECONDS,
    ):
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak percobaan masuk. Coba lagi dalam 15 menit.",
            headers={"Retry-After": str(LOGIN_WINDOW_SECONDS)},
        )

    user = repository.get_by_email(payload.email)
    demo_identity_blocked = repository.is_demo_identity(user) and not request.app.state.settings.demo_mode
    stored_hash = (
        user["password_hash"]
        if user is not None and not demo_identity_blocked
        else _DUMMY_PASSWORD_HASH
    )
    password_valid = verify_password(payload.password, stored_hash)
    if user is None or demo_identity_blocked or not password_valid:
        repository.record_login_failure(identity_hash, window_seconds=LOGIN_WINDOW_SECONDS)
        raise HTTPException(status_code=401, detail="Email atau kata sandi belum cocok.")

    repository.clear_login_failures(identity_hash)
    token = _issue_session(response, request, user["id"], repository)
    user.pop("password_hash", None)
    return _authentication_response(user, token, request)


@router.get("/me")
def me(request: Request) -> dict:
    token = _request_session_token(request)
    if not token:
        return {"user": None}
    repository = _repository(request)
    user = repository.get_user_for_session(hash_session_token(token))
    if user is not None and repository.is_demo_identity(user) and not request.app.state.settings.demo_mode:
        user = None
    return {"user": user}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    repository = _repository(request)
    tokens = {request.cookies.get(SESSION_COOKIE), _request_session_token(request)}
    for token in tokens - {None}:
        repository.delete_session(hash_session_token(token))
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
    )
    return {"ok": True}
