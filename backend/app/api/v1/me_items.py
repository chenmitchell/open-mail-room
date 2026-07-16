"""GET /api/v1/me/items -- 員工自查 (01-REQUIREMENTS.md role table: "employee:
查看自己的郵件"). Scoped to the mail_items whose recipient_employee_id
matches the Employee row linked (employees.user_id) to the logged-in user.

Also hosts POST /api/v1/me/password (M7-USERS): any logged-in user (any
role, not just employee) changing their *own* password, as distinct from
app/api/v1/admin_users.py's admin-on-someone-else reset-password. Lives
here rather than a new router since it's the same "/me" self-service
namespace and this file already has the CSRF dependency mounted
router-wide.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok, paginated
from app.api.v1._common import pagination_params
from app.api.v1.mail_items import serialize_mail_item
from app.db import get_session
from app.models.employee import Employee
from app.models.enums import MailStatus, UserRole
from app.models.mail_item import MailItem
from app.models.user import User
from app.security.csrf import require_csrf
from app.security.passwords import hash_password, verify_password
from app.security.rbac import get_current_user, require_role
from app.services.audit import record_audit

# This router only exposes GET endpoints today, but the CSRF dependency is
# mounted uniformly anyway (M1-R1 blocking #4 / "v1 router 統一掛") so any
# future write added here is automatically protected; require_csrf is a
# no-op for GET/HEAD/OPTIONS.
router = APIRouter(prefix="/me", tags=["me"], dependencies=[Depends(require_csrf)])

MIN_PASSWORD_LENGTH = 10


@router.get("/items")
async def list_my_items(
    pagination: tuple[int, int] = Depends(pagination_params),
    status: MailStatus | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(UserRole.employee)),
):
    page, size = pagination

    result = await session.execute(select(Employee).where(Employee.user_id == user.id))
    employee = result.scalar_one_or_none()
    if employee is None:
        return paginated([], total=0, page=page, size=size)

    stmt = select(MailItem).where(MailItem.recipient_employee_id == employee.id)
    count_stmt = (
        select(func.count())
        .select_from(MailItem)
        .where(MailItem.recipient_employee_id == employee.id)
    )
    if status:
        stmt = stmt.where(MailItem.status == status)
        count_stmt = count_stmt.where(MailItem.status == status)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(MailItem.received_at.desc()).offset((page - 1) * size).limit(size)
    rows = (await session.execute(stmt)).scalars().all()

    return paginated([serialize_mail_item(i) for i in rows], total=total, page=page, size=size)


class ChangeOwnPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str
    new_password: str


def _current_password_invalid() -> HTTPException:
    # 400, not 401: the caller is already authenticated (this endpoint
    # requires a valid session same as any other) -- `current_password`
    # being wrong is a bad-input-value error on this specific field, the
    # same semantic tier as WEAK_PASSWORD below, not a session/auth failure.
    return HTTPException(
        status_code=400,
        detail={
            "code": "CURRENT_PASSWORD_INVALID",
            "message": "Current password is incorrect",
        },
    )


def _weak_password() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "WEAK_PASSWORD",
            "message": f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        },
    )


@router.post("/password")
async def change_own_password(
    payload: ChangeOwnPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise _current_password_invalid()
    if len(payload.new_password) < MIN_PASSWORD_LENGTH:
        raise _weak_password()

    user.password_hash = hash_password(payload.new_password)
    session.add(user)
    await record_audit(
        session,
        request=request,
        actor=user,
        action="user.change_own_password",
        target_type="user",
        target_id=user.id,
        diff=None,
    )
    await session.commit()
    return ok({"ok": True})
