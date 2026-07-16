"""Inbound webhooks from the LINE / Telegram platforms that complete the
binding-code flow (05-NOTIFICATIONS.md section 3):

    POST /webhooks/line       verifies X-Line-Signature, matches the
                                message text against an outstanding code.
    POST /webhooks/telegram   parses "/start <code>" from the deep link.

These are called by LINE/Telegram's own servers, not by a logged-in
browser session -- there is no session cookie, so this router is
deliberately mounted *without* `Depends(require_csrf)` (same reasoning as
`/login`: CSRF's double-submit-cookie scheme has nothing to check here).
Authenticity is instead established by verifying the platform-specific
signature/secret.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok
from app.db import get_session
from app.models.enums import NotificationChannel
from app.models.notification_binding import NotificationBinding
from app.notify.adapters.line import reply_text
from app.notify.binding_codes import consume_binding_code
from app.notify.registry import (
    KEY_LINE_TOKEN,
    get_line_channel_secret,
    get_telegram_webhook_secret,
)
from app.notify.settings_store import get_setting
from app.security.rate_limit import get_webhook_ip_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["channel_webhooks"])


def _bad_signature() -> HTTPException:
    return HTTPException(
        status_code=403, detail={"code": "SIGNATURE_INVALID", "message": "Invalid signature"}
    )


def _rate_limited() -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "WEBHOOK_RATE_LIMITED",
            "message": "Too many requests to this webhook endpoint. Please try again later.",
        },
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_ip_rate_limit(request: Request, *, channel: str) -> None:
    """M3-R1 blocking #1/#2: shared per-IP request counter across every
    inbound call to this channel's webhook -- both signature/secret failures
    and binding-code guesses count toward it, since the code-guess budget in
    app/notify/binding_codes.py alone can't stop a client that never sends a
    guess matching *any* still-outstanding code (nothing there to bump)."""
    limiter = get_webhook_ip_rate_limiter(channel)
    client_ip = _client_ip(request)
    if limiter.is_locked(client_ip):
        raise _rate_limited()
    limiter.record_failure(client_ip)


async def _bind(
    session: AsyncSession, *, employee_id: str, channel: NotificationChannel, address: str
) -> NotificationBinding:
    binding = NotificationBinding(
        employee_id=employee_id,
        channel=channel,
        address=address,
        is_verified=True,
        verified_at=datetime.now(timezone.utc),
    )
    session.add(binding)
    await session.flush()
    return binding


@router.post("/line")
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None, alias="X-Line-Signature"),
    session: AsyncSession = Depends(get_session),
):
    _enforce_ip_rate_limit(request, channel="line")

    raw_body = await request.body()
    channel_secret = await get_line_channel_secret(session)
    if not channel_secret:
        # No channel secret configured yet -- nothing to verify against, so
        # nothing can be trusted. Fail closed rather than silently accepting
        # unsigned callbacks.
        raise _bad_signature()

    expected = base64.b64encode(
        hmac.new(channel_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("utf-8")
    if not x_line_signature or not hmac.compare_digest(expected, x_line_signature):
        raise _bad_signature()

    try:
        payload: dict[str, Any] = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail={"code": "BAD_REQUEST", "message": "Invalid JSON body"}
        ) from exc

    bound = 0
    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue
        message = event.get("message") or {}
        if message.get("type") != "text":
            continue
        code = str(message.get("text", "")).strip()
        user_id = (event.get("source") or {}).get("userId")
        if not code or not user_id:
            continue

        matched = await consume_binding_code(
            session, channel=NotificationChannel.line, code=code
        )
        if matched is None:
            continue

        await _bind(
            session,
            employee_id=matched.employee_id,
            channel=NotificationChannel.line,
            address=user_id,
        )
        bound += 1

        reply_token = event.get("replyToken")
        if reply_token:
            token = await get_setting(session, KEY_LINE_TOKEN, default=None)
            if token:
                await reply_text(str(token), reply_token, "綁定成功,您將會在此收到收發室通知。")

    await session.commit()
    return ok({"bound": bound})


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        default=None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
    session: AsyncSession = Depends(get_session),
):
    _enforce_ip_rate_limit(request, channel="telegram")

    configured_secret = await get_telegram_webhook_secret(session)
    if not configured_secret:
        # M3-R1 blocking #1: no secret configured means there is nothing to
        # verify the caller against -- fail closed (matching the LINE
        # handler above) instead of accepting any unauthenticated request,
        # which would let anyone hit this endpoint directly and brute-force
        # binding codes without ever going through Telegram's servers.
        raise _bad_signature()
    if not hmac.compare_digest(configured_secret, x_telegram_bot_api_secret_token or ""):
        raise _bad_signature()

    try:
        payload: dict[str, Any] = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail={"code": "BAD_REQUEST", "message": "Invalid JSON body"}
        ) from exc

    message = payload.get("message") or {}
    text = str(message.get("text", "")).strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    bound = False
    if text.startswith("/start") and chat_id is not None:
        code = text[len("/start") :].strip()
        if code:
            matched = await consume_binding_code(
                session, channel=NotificationChannel.telegram, code=code
            )
            if matched is not None:
                await _bind(
                    session,
                    employee_id=matched.employee_id,
                    channel=NotificationChannel.telegram,
                    address=str(chat_id),
                )
                bound = True

    await session.commit()
    return ok({"bound": bound})
