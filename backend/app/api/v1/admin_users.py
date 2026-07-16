"""GET|POST|PATCH /api/v1/admin/users, POST /admin/users/{id}/reset-password
-- M7-USERS admin-only login-account management.

`POST /api/v1/setup` (app/api/v1/setup.py) can only ever create the *first*
admin, once, while zero admins exist; every login account after that --
of any role, including additional admins -- is created/edited/deactivated
here instead. Admin-only end to end (require_role admin); never returns
`password_hash`/`totp_secret` (see `_serialize` below).

"Linked employee" here means `employees.user_id` (the same column
app/api/v1/auth.py's `_user_public` and app/api/v1/me_items.py's
`list_my_items` already key off of to resolve an employee's own
mail/pickup_code) pointed at this user. The FK lives on the `employees`
side, not `users`, so create/update here reach over and set/clear
`employees.user_id` directly rather than storing anything on `User` itself
-- same direction employees.py's own `_validate_user` already validates,
just driven from the other side of the relationship.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok, paginated
from app.api.v1._common import pagination_params
from app.config import get_settings
from app.db import get_session
from app.models.employee import Employee
from app.models.enums import UserRole
from app.models.user import User
from app.security.csrf import require_csrf
from app.security.passwords import hash_password
from app.security.rbac import require_role
from app.services.audit import record_audit
from app.services.user_welcome import send_welcome_email

router = APIRouter(
    prefix="/admin/users", tags=["admin_users"], dependencies=[Depends(require_csrf)]
)

ADMIN_ONLY = (UserRole.admin,)
MIN_PASSWORD_LENGTH = 10


def _weak_password() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "WEAK_PASSWORD",
            "message": f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        },
    )


def _email_exists() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "EMAIL_EXISTS", "message": "email already in use"},
    )


def _user_not_found() -> HTTPException:
    return HTTPException(
        status_code=404, detail={"code": "USER_NOT_FOUND", "message": "User not found"}
    )


def _employee_not_found() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": "EMPLOYEE_NOT_FOUND", "message": "employee_id does not exist"},
    )


def _last_admin() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "LAST_ADMIN",
            "message": "Cannot demote or deactivate the last active admin",
        },
    )


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise ValueError("Invalid email address")
    return value


def _non_blank_display_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("display_name is required")
    if len(value) > 255:
        raise ValueError("display_name is too long")
    return value


class AdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    display_name: str
    role: UserRole
    password: str
    employee_id: str | None = None

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("display_name")
    @classmethod
    def _display_name_shape(cls, value: str) -> str:
        return _non_blank_display_name(value)


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    employee_id: str | None = None


class AdminUserResetPassword(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str


def _serialize(user: User, *, employee: Employee | None = None) -> dict[str, Any]:
    """Never includes `password_hash`/`totp_secret` -- this is the only
    shape /admin/users ever hands back."""
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role.value,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "employee_id": employee.id if employee is not None else None,
        "employee_name": employee.name if employee is not None else None,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }


async def _get_user_or_404(session: AsyncSession, user_id: str) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise _user_not_found()
    return user


async def _get_employee_or_400(session: AsyncSession, employee_id: str) -> Employee:
    emp = await session.get(Employee, employee_id)
    if emp is None:
        raise _employee_not_found()
    return emp


async def _linked_employee(session: AsyncSession, user_id: str) -> Employee | None:
    result = await session.execute(select(Employee).where(Employee.user_id == user_id))
    return result.scalar_one_or_none()


async def _relink_employee(
    session: AsyncSession, user: User, employee_id: str | None
) -> Employee | None:
    """Point `employees.user_id` at `user` (or clear it, if `employee_id`
    is None). Any employee previously linked to this user that isn't the
    new target is unlinked first -- `employees.user_id` has no DB-level
    unique constraint (app/models/employee.py), so this is enforced here to
    keep the "one employee per login account" convention every other caller
    of this column already assumes (auth.py's `_user_public`,
    me_items.py's `list_my_items`)."""
    current = await _linked_employee(session, user.id)
    if current is not None and (employee_id is None or current.id != employee_id):
        current.user_id = None
        session.add(current)

    if employee_id is None:
        return None

    new_employee = await _get_employee_or_400(session, employee_id)
    new_employee.user_id = user.id
    session.add(new_employee)
    return new_employee


async def _active_admin_count(session: AsyncSession, *, exclude_user_id: str | None = None) -> int:
    stmt = select(func.count()).select_from(User).where(
        User.role == UserRole.admin, User.is_active.is_(True)
    )
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    result = await session.execute(stmt)
    return int(result.scalar_one())


@router.get("")
async def list_users(
    pagination: tuple[int, int] = Depends(pagination_params),
    q: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_role(*ADMIN_ONLY)),
):
    page, size = pagination
    stmt = select(User, Employee).outerjoin(Employee, Employee.user_id == User.id)
    count_stmt = select(func.count()).select_from(User)

    conditions = []
    if q:
        like = f"%{q}%"
        conditions.append(or_(User.email.ilike(like), User.display_name.ilike(like)))
    if role:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active == is_active)

    for cond in conditions:
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(User.email).offset((page - 1) * size).limit(size)
    rows = (await session.execute(stmt)).all()

    return paginated(
        [_serialize(u, employee=emp) for u, emp in rows], total=total, page=page, size=size
    )


@router.post("", status_code=201)
async def create_user(
    payload: AdminUserCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_role(*ADMIN_ONLY)),
):
    if len(payload.password) < MIN_PASSWORD_LENGTH:
        raise _weak_password()

    employee: Employee | None = None
    if payload.employee_id is not None:
        employee = await _get_employee_or_400(session, payload.employee_id)

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        role=payload.role,
        is_active=True,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise _email_exists() from exc

    if employee is not None:
        employee.user_id = user.id
        session.add(employee)
        await session.flush()

    await record_audit(
        session,
        request=request,
        actor=admin,
        action="user.create",
        target_type="user",
        target_id=user.id,
        diff={
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role.value,
            "employee_id": employee.id if employee is not None else None,
        },
    )
    await session.commit()
    await session.refresh(user)

    # M10: best-effort welcome email so the new user can sign in and change
    # their own password. Never fails account creation (SMTP not configured or
    # a delivery error just yields welcome_email_sent=False).
    settings = get_settings()
    base = (settings.public_base_url or str(request.base_url)).rstrip("/")
    welcome_sent = await send_welcome_email(
        email=user.email,
        display_name=user.display_name,
        initial_password=payload.password,
        login_url=f"{base}/login",
    )
    body = _serialize(user, employee=employee)
    body["welcome_email_sent"] = welcome_sent
    return ok(body)


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_role(*ADMIN_ONLY)),
):
    target = await _get_user_or_404(session, user_id)
    before_employee = await _linked_employee(session, target.id)
    before = _serialize(target, employee=before_employee)

    updates = payload.model_dump(exclude_unset=True)

    # Anti-lockout (task brief): refuse to demote/deactivate the last
    # remaining *active* admin -- whether the caller is doing it to
    # themselves or to someone else, the failure mode ("nobody left who can
    # administer the system") is identical either way, so one check covers
    # both cases without needing to special-case "is this actor == target".
    will_lose_admin = ("role" in updates and updates["role"] != UserRole.admin) or (
        "is_active" in updates and updates["is_active"] is False
    )
    if will_lose_admin and target.role == UserRole.admin and target.is_active:
        remaining = await _active_admin_count(session, exclude_user_id=target.id)
        if remaining == 0:
            raise _last_admin()

    if "display_name" in updates:
        target.display_name = updates["display_name"]
    if "role" in updates:
        target.role = updates["role"]
    if "is_active" in updates:
        target.is_active = updates["is_active"]
    session.add(target)

    employee = before_employee
    if "employee_id" in updates:
        employee = await _relink_employee(session, target, updates["employee_id"])

    await session.flush()

    after = _serialize(target, employee=employee)
    await record_audit(
        session,
        request=request,
        actor=admin,
        action="user.update",
        target_type="user",
        target_id=target.id,
        diff={"before": before, "after": after},
    )
    await session.commit()
    await session.refresh(target)
    return ok(_serialize(target, employee=employee))


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    payload: AdminUserResetPassword,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_role(*ADMIN_ONLY)),
):
    if len(payload.new_password) < MIN_PASSWORD_LENGTH:
        raise _weak_password()

    target = await _get_user_or_404(session, user_id)
    target.password_hash = hash_password(payload.new_password)
    session.add(target)

    await record_audit(
        session,
        request=request,
        actor=admin,
        action="user.reset_password",
        target_type="user",
        target_id=target.id,
        diff=None,
    )
    await session.commit()
    await session.refresh(target)
    employee = await _linked_employee(session, target.id)
    return ok(_serialize(target, employee=employee))


__all__ = ["router"]
