"""Session JWTs (15 minute lifetime, HS256), carried in an HttpOnly cookie."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import get_settings

SESSION_COOKIE_NAME = "session"
CSRF_COOKIE_NAME = "csrf_token"
ALGORITHM = "HS256"


class InvalidSessionToken(Exception):
    pass


def create_session_token(
    user_id: str, role: str, *, expires_minutes: int | None = None
) -> str:
    settings = get_settings()
    if expires_minutes is not None:
        minutes = expires_minutes
    else:
        minutes = settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "type": "session",
    }
    return jwt.encode(payload, settings.require_secret_key(), algorithm=ALGORITHM)


def decode_session_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.require_secret_key(), algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidSessionToken(str(exc)) from exc
