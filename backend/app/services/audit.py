"""Append-only audit trail helper.

01-REQUIREMENTS.md section 4 / 02-DATA-MODEL.md: every create/modify/status
change, and every view of a confidential mail_item, must write an
audit_logs row. This module centralizes that so routers don't hand-roll the
actor/ip/user-agent extraction differently in different places.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.enums import ActorType
from app.models.user import User


def _client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("user-agent")


async def record_audit(
    session: AsyncSession,
    *,
    request: Request | None,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: str | None,
    diff: dict[str, Any] | None = None,
    actor_type: ActorType = ActorType.user,
    flush: bool = True,
) -> AuditLog:
    entry = AuditLog(
        actor_type=actor_type,
        actor_id=actor.id if actor is not None else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        diff_json=diff,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    session.add(entry)
    if flush:
        await session.flush()
    return entry
