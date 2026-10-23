from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.responses import JSONResponse

ASGIApp = Callable[..., Awaitable[None]]


class RequestBodyLimitMiddleware:
    """Buffer and cap API request bodies before parsing JSON or base64 photos."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                declared_length = int(raw_length)
            except ValueError:
                declared_length = 0
            if declared_length > self.max_bytes:
                await self._reject(scope, receive, send)
                return

        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.max_bytes:
                await self._reject(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        replayed = False

        async def replay_receive():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(scope, receive, send) -> None:
        response = JSONResponse(
            {"detail": "Ukuran permintaan melebihi batas yang diizinkan."},
            status_code=413,
        )
        await response(scope, receive, send)


class SecurityHeadersMiddleware:
    """Apply conservative response headers to the JSON API and prevent caching."""

    def __init__(self, app: ASGIApp, app_env: str) -> None:
        self.app = app
        self.app_env = app_env

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def add_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                values = {
                    b"cache-control": b"no-store, max-age=0",
                    b"pragma": b"no-cache",
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"strict-origin-when-cross-origin",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=(), payment=(), usb=()",
                    b"cross-origin-resource-policy": b"same-origin",
                    b"content-security-policy": b"default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
                }
                if self.app_env == "production":
                    values[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                current_names = {key.lower() for key, _ in headers}
                headers.extend(
                    (key, value)
                    for key, value in values.items()
                    if key not in current_names
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, add_headers)
