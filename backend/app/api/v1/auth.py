from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok
from app.config import get_settings
from app.db import get_session
from app.models.department import Department
from app.models.employee import Employee
from app.models.user import User
from app.security.csrf import (
    CSRF_HEADER_NAME,
    generate_csrf_token,
    require_csrf,
)
from app.security.jwt import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, create_session_token
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.rate_limit import get_ip_rate_limiter, get_login_rate_limiter
from app.security.rbac import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _basic_email_shape(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Invalid email address")
        return value


async def _user_public(session: AsyncSession, user: User) -> dict:
    # M3-R1 blocking #5: when this user account is linked to an `employees`
    # row (employees.user_id, same linkage app/api/v1/me_items.py uses),
    # surface that employee's `pickup_code` and department name here --
    # frontend/src/pages/employee/MyMailPage.vue's "取件碼大字" has nowhere
    # else to read it from (src/types/api.ts `AuthUser.pickup_code` /
    # `.department` were already typed for this, pending this backend fix).
    # `None` for accounts with no linked employee record (e.g. counter/admin
    # logins with no directory entry).
    employee_id: str | None = None
    pickup_code: str | None = None
    department_name: str | None = None
    result = await session.execute(select(Employee).where(Employee.user_id == user.id))
    employee = result.scalar_one_or_none()
    if employee is not None:
        employee_id = employee.id
        pickup_code = employee.pickup_code
        if employee.department_id:
            dept_result = await session.execute(
                select(Department).where(Department.id == employee.department_id)
            )
            department = dept_result.scalar_one_or_none()
            department_name = department.name if department is not None else None

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role.value,
        "is_active": user.is_active,
        # M4-R1: the caller's own employee id, via the same employees.user_id
        # linkage as pickup_code above. Without it the outbound page had to
        # *guess* who the requester was by fuzzy-matching their display name
        # against the directory, and auto-filled the top hit at score >= 90.
        # Two employees sharing a name (not rare with Chinese names) made that
        # guess arbitrary -- the tie-break was just SQL row order -- so a
        # counter filing a request on someone's behalf could silently attribute
        # it to the wrong person. An exact id the user already owns removes the
        # guess entirely.
        "employee_id": employee_id,
        "pickup_code": pickup_code,
        "department": department_name,
    }


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_session_cookies(response: Response, *, token: str, csrf_token: str) -> None:
    settings = get_settings()
    secure = settings.environment != "development"
    max_age = settings.access_token_expire_minutes * 60
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    limiter = get_login_rate_limiter()
    ip_limiter = get_ip_rate_limiter()
    client_ip = _client_ip(request)
    key = f"{client_ip}:{payload.email}"

    # Per-IP spray guard checked first (M0-R1 blocking #6): 5 failures/60s
    # from one IP is blocked regardless of which email(s) it targeted, in
    # addition to the existing per-(ip,email) account lockout below.
    if ip_limiter.is_locked(client_ip) or limiter.is_locked(key):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "AUTH_RATE_LIMITED",
                "message": "Too many failed login attempts. Please try again later.",
            },
        )

    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        password_ok = False
    else:
        password_ok = verify_password(payload.password, user.password_hash)

    if not password_ok:
        limiter.record_failure(key)
        ip_limiter.record_failure(client_ip)
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_INVALID", "message": "Invalid email or password"},
        )

    limiter.reset(key)
    if needs_rehash(user.password_hash):
        # argon2 parameters may have been tightened since this hash was
        # created; opportunistically rehash on a successful login so
        # password storage strength stays current (M0-R1 suggestion).
        user.password_hash = hash_password(payload.password)
    user.last_login_at = datetime.now(timezone.utc)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    token = create_session_token(user.id, user.role.value)
    csrf_token = generate_csrf_token()
    _set_session_cookies(response, token=token, csrf_token=csrf_token)

    return ok(await _user_public(session, user))


@router.post("/logout")
async def logout(
    response: Response,
    user: User = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    _clear_session_cookies(response)
    return ok({"logged_out": True})


@router.get("/me")
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return ok(await _user_public(session, user))


__all__ = ["router", "CSRF_HEADER_NAME"]
