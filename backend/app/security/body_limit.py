"""Generic request-body size ceiling, enforced at the ASGI layer.

M1-R1 blocking #1: relying only on `Content-Length` (or on each endpoint
remembering to check a size after fully buffering the body) is not enough --
`Content-Length` can be absent/spoofed under chunked transfer-encoding, and
FastAPI/Starlette fully buffer JSON and multipart bodies into memory before
handler code ever runs. This middleware sits outside all of that: it rejects
a declared `Content-Length` over the limit immediately (fast path, no body
read at all), and also counts bytes as they stream in so a request that
lies about its size (or omits the header) still gets cut off instead of
being buffered without bound.

Deliberately implemented as a plain ASGI middleware (not
`starlette.middleware.base.BaseHTTPMiddleware`, which itself buffers the
whole body to hand the handler a `Request` object -- defeating the point).
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.envelope import fail

# Generic ceiling for *any* request body under this app. Specific endpoints
# (CSV import, pickup signature) enforce tighter, purpose-specific limits on
# top of this via app.security.upload_limits; this is the backstop so no
# endpoint can ever be missed.
MAX_REQUEST_BODY_BYTES = 20 * 1024 * 1024  # 20 MB


class _BodyTooLarge(Exception):
    pass


def _too_large_response(max_bytes: int) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content=fail(
            "UPLOAD_TOO_LARGE",
            f"Request body exceeds the {max_bytes} byte limit",
        ),
    )


class BodySizeLimitMiddleware:
    """`path_overrides` maps a path prefix to a larger-than-default ceiling
    (M2-01: `POST /uploads` legitimately needs up to `30 * 15MB`, far past
    this middleware's generic 20MB default -- see
    app.security.upload_limits.MAX_UPLOAD_BATCH_BYTES). The first matching
    prefix wins; anything not matched falls back to `max_bytes`.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int = MAX_REQUEST_BODY_BYTES,
        path_overrides: dict[str, int] | None = None,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path_overrides = path_overrides or {}

    def _limit_for(self, path: str) -> int:
        for prefix, limit in self.path_overrides.items():
            if path.startswith(prefix):
                return limit
        return self.max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = self._limit_for(scope.get("path", ""))

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = None
            if declared is not None and declared > max_bytes:
                await _too_large_response(max_bytes)(scope, receive, send)
                return

        total = 0

        async def guarded_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b"") or b"")
                if total > max_bytes:
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, guarded_receive, send)
        except _BodyTooLarge:
            await _too_large_response(max_bytes)(scope, receive, send)
