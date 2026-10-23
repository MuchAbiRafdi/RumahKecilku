from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from app.core.security import hash_session_token


SESSION_COOKIE = "rumah_kecilku_session"


def _session_token(request: Request) -> str | None:
    settings = request.app.state.settings
    if settings.app_env == "preview" and settings.demo_mode and settings.browser_session_token:
        # Browser bearer tokens are accepted only in the synthetic embedded preview.
        preview_token = (request.headers.get("x-rumah-kecilku-session") or "").strip()
        if preview_token:
            return preview_token
        authorization = request.headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if separator and scheme.lower() == "bearer" and token.strip():
            return token.strip()
    return request.cookies.get(SESSION_COOKIE)


def get_current_user(request: Request) -> dict:
    token = _session_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Silakan masuk untuk membuka ruang kerja.",
        )
    user = request.app.state.auth_repository.get_user_for_session(hash_session_token(token))
    settings = request.app.state.settings
    if user is not None and request.app.state.auth_repository.is_demo_identity(user) and not settings.demo_mode:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi demo tidak tersedia di lingkungan ini.",
        )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi berakhir. Silakan masuk kembali.",
        )
    return user


def require_roles(*allowed_roles: str) -> Callable:
    def require_role(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Peran akun ini tidak memiliki akses ke ruang tersebut.",
            )
        return user

    return require_role
