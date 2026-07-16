"""Employee self-service notification bindings (03-API-SPEC.md section 2
"通知綁定(員工自助)" / 05-NOTIFICATIONS.md section 3):

    POST   /me/bindings/{channel}/start   channel in {line, telegram}: issue
                                            a 6-digit code (10 min TTL); the
                                            actual binding is completed by
                                            the employee messaging the bot,
                                            handled by
                                            app/api/v1/channel_webhooks.py.
    POST   /me/bindings/{channel}         channel in {email, slack, discord,
                                            webhook}: direct bind with an
                                            address supplied in the body
                                            (M3-R1 blocking #4: `channel` is a
                                            path parameter here, matching
                                            03-API-SPEC.md section 2 and
                                            frontend/src/api/bindings.ts --
                                            it was previously accepted only
                                            in the JSON body, which the
                                            frontend never sent and always
                                            404'd against).
    GET    /me/bindings                   list the caller's own bindings.
    DELETE /me/bindings/{id}              remove one of the caller's own
                                            bindings.

Every logged-in user who has a linked `employees` row (employees.user_id)
may manage their own bindings -- this isn't role-gated beyond "must be
logged in", since it's inherently self-service (an admin with no employee
record has nothing to bind).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok
from app.db import get_session
from app.models.employee import Employee
from app.models.enums import NotificationChannel
from app.models.notification_binding import NotificationBinding
from app.models.user import User
from app.notify.binding_codes import CODE_TTL_MINUTES, issue_binding_code
from app.notify.registry import KEY_TELEGRAM_BOT_USERNAME
from app.notify.settings_store import get_setting
from app.security.csrf import require_csrf
from app.security.rbac import get_current_user
from app.security.ssrf import UnsafeBaseUrlError, check_base_url_allowed
from app.services.audit import record_audit

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter(prefix="/me/bindings", tags=["bindings"], dependencies=[Depends(require_csrf)])

_CODE_CHANNELS = (NotificationChannel.line, NotificationChannel.telegram)
_DIRECT_CHANNELS = (
    NotificationChannel.email,
    NotificationChannel.slack,
    NotificationChannel.discord,
    NotificationChannel.webhook,
)
_URL_CHANNELS = (
    NotificationChannel.slack,
    NotificationChannel.discord,
    NotificationChannel.webhook,
)


def _mask_address(address: str) -> str:
    """M3-R1 suggestion (adopted): never echo a binding's full address back
    over the API -- mirrors the "key 只寫不讀,回遮罩 sk-***abc" convention
    already used for ai_provider_configs/admin webhook secrets. Keeps a
    couple of characters on each end (enough for the employee to recognise
    *which* address/URL/chat this row is, e.g. "jo***@example.com" or
    "Ua***23") and masks everything in between; short values are masked
    entirely rather than revealing most of a 4-character string."""
    if len(address) <= 4:
        return "*" * len(address)
    return f"{address[:2]}{'*' * (len(address) - 4)}{address[-2:]}"


def _serialize(binding: NotificationBinding) -> dict[str, Any]:
    return {
        "id": binding.id,
        "channel": binding.channel.value,
        "address": _mask_address(binding.address),
        "is_verified": binding.is_verified,
        "verified_at": binding.verified_at.isoformat() if binding.verified_at else None,
        "created_at": binding.created_at.isoformat(),
    }


async def _current_employee(session: AsyncSession, user: User) -> Employee:
    result = await session.execute(select(Employee).where(Employee.user_id == user.id))
    employee = result.scalar_one_or_none()
    if employee is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "EMPLOYEE_NOT_FOUND",
                "message": "This user account has no linked employee record",
            },
        )
    return employee


class DirectBindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(min_length=1, max_length=1024)


def _bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": code, "message": message})


@router.post("/{channel}/start", status_code=201)
async def start_binding(
    channel: NotificationChannel,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if channel not in _CODE_CHANNELS:
        raise _bad_request(
            "BINDING_CHANNEL_UNSUPPORTED",
            f"'{channel.value}' does not use the binding-code flow; "
            "use POST /me/bindings/{channel}",
        )
    employee = await _current_employee(session, user)
    row = await issue_binding_code(session, employee_id=employee.id, channel=channel)
    await session.commit()

    body: dict[str, Any] = {
        "code": row.code,
        "channel": channel.value,
        "expires_at": row.expires_at.isoformat(),
        "ttl_minutes": CODE_TTL_MINUTES,
    }
    if channel == NotificationChannel.telegram:
        bot_username = await get_setting(session, KEY_TELEGRAM_BOT_USERNAME, default=None)
        if bot_username:
            body["deep_link"] = f"https://t.me/{bot_username}?start={row.code}"
    return ok(body)


@router.post("/{channel}", status_code=201)
async def create_direct_binding(
    channel: NotificationChannel,
    payload: DirectBindingCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if channel not in _DIRECT_CHANNELS:
        raise _bad_request(
            "BINDING_CHANNEL_UNSUPPORTED",
            f"'{channel.value}' must be bound via POST /me/bindings/{{channel}}/start",
        )
    employee = await _current_employee(session, user)

    if channel == NotificationChannel.email and not _EMAIL_RE.match(payload.address):
        raise _bad_request("BINDING_ADDRESS_INVALID", "address is not a valid email")

    if channel in _URL_CHANNELS:
        try:
            check_base_url_allowed(payload.address, allow_private_network=False)
        except UnsafeBaseUrlError as exc:
            raise _bad_request("BINDING_ADDRESS_UNSAFE", str(exc)) from exc
        if not payload.address.lower().startswith("https://"):
            raise _bad_request(
                "BINDING_ADDRESS_UNSAFE", "webhook/slack/discord addresses must use https://"
            )

    binding = NotificationBinding(
        employee_id=employee.id,
        channel=channel,
        address=payload.address,
        is_verified=True,
        verified_at=datetime.now(timezone.utc),
    )
    session.add(binding)
    await session.flush()

    await record_audit(
        session,
        request=request,
        actor=user,
        action="notification_binding.create",
        target_type="notification_binding",
        target_id=binding.id,
        diff={"channel": binding.channel.value},
    )
    await session.commit()
    await session.refresh(binding)
    return ok(_serialize(binding))


@router.get("")
async def list_my_bindings(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    employee = await _current_employee(session, user)
    rows = (
        (
            await session.execute(
                select(NotificationBinding).where(NotificationBinding.employee_id == employee.id)
            )
        )
        .scalars()
        .all()
    )
    return ok([_serialize(b) for b in rows])


@router.delete("/{binding_id}")
async def delete_binding(
    binding_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    employee = await _current_employee(session, user)
    binding = await session.get(NotificationBinding, binding_id)
    if binding is None or binding.employee_id != employee.id:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "Binding not found"}
        )
    await session.delete(binding)
    await record_audit(
        session,
        request=request,
        actor=user,
        action="notification_binding.delete",
        target_type="notification_binding",
        target_id=binding_id,
        diff={"channel": binding.channel.value},
    )
    await session.commit()
    return ok({"deleted": True})
