"""GET /api/v1/admin/audit-logs -- 03-API-SPEC.md section 2 "管理",
01-REQUIREMENTS.md role table ("admin: ... 稽核紀錄").

Admin-only, paginated, filterable by actor/action/target/date -- audit_logs
itself is append-only (app/models/audit_log.py blocks UPDATE/DELETE at the
ORM level), so this is a pure read path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import paginated
from app.api.v1._common import pagination_params
from app.db import get_session
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.models.enums import ActorType, UserRole
from app.models.user import User
from app.security.csrf import require_csrf
from app.security.rbac import require_role

router = APIRouter(
    prefix="/admin/audit-logs", tags=["admin_audit"], dependencies=[Depends(require_csrf)]
)

ADMIN_ONLY = (UserRole.admin,)


def _serialize(entry: AuditLog, actor_name: str | None = None) -> dict[str, Any]:
    """`actor_name` is resolved by the caller's join, not looked up here.

    An audit trail whose "who" column is a raw UUID is an audit trail nobody
    reads -- the whole point is that an admin can answer "who changed this?"
    without a second lookup. `audit_logs` deliberately stores only `actor_id`
    (it is append-only, and denormalizing a name into it would freeze a name
    that can legitimately change), so the name is resolved at read time
    instead: a user's display_name, or an API key's name. `system` actors have
    no id and stay null, which reads correctly as "the system did this".
    """
    return {
        "id": entry.id,
        "actor_type": entry.actor_type.value,
        "actor_id": entry.actor_id,
        "actor_name": actor_name,
        "action": entry.action,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "diff_json": entry.diff_json,
        "ip": entry.ip,
        "user_agent": entry.user_agent,
        "at": entry.at.isoformat(),
    }


@router.get("")
async def list_audit_logs(
    pagination: tuple[int, int] = Depends(pagination_params),
    actor_id: str | None = None,
    actor_type: ActorType | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*ADMIN_ONLY)),
):
    page, size = pagination
    # One join per actor kind rather than N lookups per page. actor_id is a
    # plain string, so at most one of these matches for any given row.
    stmt = (
        select(AuditLog, User.display_name, ApiKey.name)
        .outerjoin(User, AuditLog.actor_id == User.id)
        .outerjoin(ApiKey, AuditLog.actor_id == ApiKey.id)
    )
    count_stmt = select(func.count()).select_from(AuditLog)

    conditions = []
    if actor_id:
        conditions.append(AuditLog.actor_id == actor_id)
    if actor_type:
        conditions.append(AuditLog.actor_type == actor_type)
    if action:
        conditions.append(AuditLog.action.ilike(f"%{action}%"))
    if target_type:
        conditions.append(AuditLog.target_type == target_type)
    if target_id:
        conditions.append(AuditLog.target_id == target_id)
    if date_from:
        conditions.append(AuditLog.at >= date_from)
    if date_to:
        conditions.append(AuditLog.at <= date_to)

    for cond in conditions:
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(AuditLog.at.desc()).offset((page - 1) * size).limit(size)
    rows = (await session.execute(stmt)).all()

    return paginated(
        [
            _serialize(entry, user_name or api_key_name)
            for entry, user_name, api_key_name in rows
        ],
        total=total,
        page=page,
        size=size,
    )
