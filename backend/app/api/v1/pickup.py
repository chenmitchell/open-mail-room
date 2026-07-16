"""POST /api/v1/pickup/lookup -- dedicated pickup-code lookup endpoint for
the counter's 核銷 (verification) flow (06-UI-UX.md §1 "輸入取件碼").

M1-R1 blocking #3: `GET /employees` no longer returns `pickup_code` at all
(see app/api/v1/employees.py), and even before that fix, the frontend's
"look up by code" flow was calling `GET /employees?q=<code>` -- which only
ever searches the `name` column, so it never actually worked. This endpoint
replaces that: the code is compared server-side, in constant time
(`hmac.compare_digest`), against every employee's *actual* `pickup_code`,
with IP+code failure-count rate limiting (M1-R1 suggestion) so it can't be
used to brute-force codes.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok
from app.api.v1.mail_items import ACTIVE_SOURCE_STATUSES, serialize_mail_item
from app.db import get_session
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import UserRole
from app.models.mail_item import MailItem
from app.models.user import User
from app.security.csrf import require_csrf
from app.security.rate_limit import get_pickup_code_ip_rate_limiter, get_pickup_code_rate_limiter
from app.security.rbac import require_role

router = APIRouter(prefix="/pickup", tags=["pickup"], dependencies=[Depends(require_csrf)])

LOOKUP_ROLES = (UserRole.admin, UserRole.counter)


class PickupLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pickup_code: str = Field(min_length=1, max_length=64)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _invalid() -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": "PICKUP_CODE_INVALID",
            "message": "pickup_code does not match any employee",
        },
    )


def _rate_limited() -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "PICKUP_CODE_RATE_LIMITED",
            "message": "Too many failed pickup-code lookups. Please try again later.",
        },
    )


@router.post("/lookup")
async def lookup_by_pickup_code(
    payload: PickupLookupRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*LOOKUP_ROLES)),
):
    ip_limiter = get_pickup_code_ip_rate_limiter()
    code_limiter = get_pickup_code_rate_limiter()
    client_ip = _client_ip(request)
    code_key = f"{client_ip}:{payload.pickup_code}"

    if ip_limiter.is_locked(client_ip) or code_limiter.is_locked(code_key):
        raise _rate_limited()

    # No indexed equality lookup on pickup_code: we want a constant-time
    # comparison against the candidate, not a DB index seek that would leak
    # nothing extra here anyway (pickup_code is an opaque random string, not
    # a secret derived from anything worth timing-attacking at the SQL
    # layer) -- the real point of compare_digest is avoiding a short-circuit
    # Python `==` once we're down to comparing byte-by-byte in application
    # code.
    result = await session.execute(
        select(Employee, Department.name).outerjoin(
            Department, Employee.department_id == Department.id
        )
    )
    match: Employee | None = None
    department_name: str | None = None
    for employee, dept_name in result.all():
        if employee.pickup_code and hmac.compare_digest(employee.pickup_code, payload.pickup_code):
            match = employee
            department_name = dept_name
            break

    if match is None:
        ip_limiter.record_failure(client_ip)
        code_limiter.record_failure(code_key)
        raise _invalid()

    ip_limiter.reset(client_ip)
    code_limiter.reset(code_key)

    items_stmt = (
        select(MailItem)
        .where(
            MailItem.recipient_employee_id == match.id,
            MailItem.status.in_(ACTIVE_SOURCE_STATUSES),
        )
        .order_by(MailItem.received_at.asc())
    )
    items = (await session.execute(items_stmt)).scalars().all()

    return ok(
        {
            "employee": {
                "id": match.id,
                "name": match.name,
                "department_id": match.department_id,
                "department_name": department_name,
            },
            "items": [serialize_mail_item(i) for i in items],
        }
    )
