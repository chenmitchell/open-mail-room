"""CSRF double-submit cookie check.

The `csrf_token` cookie is set (readable by JS, i.e. not HttpOnly) whenever a
session is established. State-changing requests must echo the same value
back in the `X-CSRF-Token` header; we compare the two with a constant-time
comparison.

M1-R1 blocking #4: every write endpoint needs this, not just `/logout`. To
guarantee that consistently (rather than relying on remembering to add
`Depends(require_csrf)` to every new endpoint one by one), each mutating
sub-router is mounted with `dependencies=[Depends(require_csrf)]` at the
router level (see app/api/v1/*.py) -- i.e. "v1 router 統一掛" -- with only
`/login` and `/healthz` exempt (login has no session/csrf cookie yet;
healthz is unauthenticated and outside /api/v1 entirely). For that to be
safe to mount router-wide without breaking GET/HEAD/OPTIONS reads (which
legitimately never carry the header), this dependency is a no-op for safe
HTTP methods.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import Header, HTTPException, Request

from app.security.jwt import CSRF_COOKIE_NAME

CSRF_HEADER_NAME = "X-CSRF-Token"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


async def require_csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER_NAME),
) -> None:
    if request.method in _SAFE_METHODS:
        return
    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    if not cookie_value or not x_csrf_token or not hmac.compare_digest(cookie_value, x_csrf_token):
        raise HTTPException(
            status_code=403,
            detail={"code": "CSRF_INVALID", "message": "Missing or mismatched CSRF token"},
        )
