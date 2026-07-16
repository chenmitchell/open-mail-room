"""GET /api/v1/setup/status, POST /api/v1/setup -- first-run "create the
initial administrator" wizard (SETUP-WIZARD).

Previously the only way to get an admin account was scripts/seed.py
auto-generating one with a random password printed once to the deploy log
(easy to miss/lose, and printed to a log stream operators don't always
tightly control access to). This replaces that default with a
Gitea/Nextcloud-style first-visit setup page: as long as zero `role=admin`
users exist, whoever reaches this API first can create exactly one admin
account with a password *they* choose. Once that first admin exists, this
endpoint is permanently locked (409 SETUP_ALREADY_DONE) -- there is no way
to create a *second* admin through this endpoint; use the normal
(session + RBAC protected) user-management flow for that.

No session exists yet at this point in the app's life, so neither of the
usual protections apply the normal way:
- CSRF: `require_csrf` is a double-submit-cookie check against the
  `csrf_token` cookie set at login -- there is no session yet, so (like
  `POST /auth/login`) POST /setup is exempt. The one-shot nature of the
  bootstrap (only ever succeeds once) plus the rate limiter below is the
  mitigation instead.
- RBAC: nobody is logged in yet, by definition.
- Rate limiting (per-IP, reusing app.security.rate_limit's LoginRateLimiter
  shape) is the abuse guard that *is* still in effect.

Does not auto-login on success (01-REQUIREMENTS.md-style least-surprise: a
freshly created admin should go through the normal login flow, same as any
other account) -- the frontend redirects to /login after a successful
POST.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok
from app.db import get_session
from app.models.enums import ActorType, UserRole
from app.models.user import User
from app.security.passwords import hash_password
from app.security.rate_limit import get_setup_rate_limiter
from app.services.audit import record_audit

router = APIRouter(prefix="/setup", tags=["setup"])

MIN_PASSWORD_LENGTH = 10

# Serializes the "check admin count -> create" critical section within this
# process. This project already assumes a single-container deployment (see
# app/security/rate_limit.py's LoginRateLimiter docstring: "Not distributed
# -- fine for the single-container deployment target of this project") --
# this lock closes the same-process race where two concurrent
# `POST /setup` requests both observe zero admins and both try to create
# one before either commits.
_setup_lock = asyncio.Lock()


class SetupCreateAdminRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    display_name: str
    password: str

    @field_validator("email")
    @classmethod
    def _basic_email_shape(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Invalid email address")
        return value

    @field_validator("display_name")
    @classmethod
    def _non_blank_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("display_name is required")
        if len(value) > 255:
            raise ValueError("display_name is too long")
        return value


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limited() -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "SETUP_RATE_LIMITED",
            "message": "Too many setup attempts. Please try again later.",
        },
    )


def _already_done() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "SETUP_ALREADY_DONE",
            "message": "An administrator already exists; the setup wizard is locked.",
        },
    )


def _password_too_weak() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "PASSWORD_TOO_WEAK",
            "message": f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        },
    )


def _email_taken() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "SETUP_EMAIL_TAKEN", "message": "email already in use"},
    )


async def _admin_count(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count()).select_from(User).where(User.role == UserRole.admin)
    )
    return int(result.scalar_one())


async def _needs_setup(session: AsyncSession) -> bool:
    return await _admin_count(session) == 0


@router.get("/status")
async def setup_status(session: AsyncSession = Depends(get_session)):
    return ok({"needs_setup": await _needs_setup(session)})


@router.post("")
async def setup_create_admin(
    payload: SetupCreateAdminRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    limiter = get_setup_rate_limiter()
    client_ip = _client_ip(request)
    if limiter.is_locked(client_ip):
        raise _rate_limited()

    async with _setup_lock:
        if not await _needs_setup(session):
            limiter.record_failure(client_ip)
            raise _already_done()

        if len(payload.password) < MIN_PASSWORD_LENGTH:
            limiter.record_failure(client_ip)
            raise _password_too_weak()

        user = User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
            role=UserRole.admin,
            is_active=True,
        )
        session.add(user)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            limiter.record_failure(client_ip)
            raise _email_taken() from exc

        await record_audit(
            session,
            request=request,
            actor=None,
            actor_type=ActorType.system,
            action="setup.create_admin",
            target_type="user",
            target_id=user.id,
            diff={"email": user.email, "display_name": user.display_name},
        )
        await session.commit()

    limiter.reset(client_ip)
    return ok({"ok": True})


__all__ = ["router"]
