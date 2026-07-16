"""Outbound event publisher for admin-subscribed `webhook_endpoints`
(03-API-SPEC.md section 3).

Delivery is launched fire-and-forget from the request handler that changed
the mail item's state (mirrors app/ocr/pipeline.py's background-task shape:
`asyncio.create_task(...)`, kept alive via a module-level strong-reference
set so it isn't GC'd mid-flight). The task opens its *own* DB session (the
request's session may already be closed/committed-and-gone by the time HTTP
retries finish) and retries each endpoint up to `MAX_ATTEMPTS` times with
exponential backoff; `CONSECUTIVE_FAIL_DISABLE` consecutive failures across
*calls* (not just this one event) auto-disables the endpoint and alerts
admin, per "連續失敗 20 次自動停用並通知 admin".
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.models.mail_item import MailItem
from app.models.outbound_item import OutboundItem
from app.models.webhook_endpoint import WebhookEndpoint
from app.notify.admin_alert import alert_admin
from app.notify.http import send_http
from app.security.ssrf import UnsafeBaseUrlError, check_base_url_allowed
from app.webhooks.payload import build_event_payload, build_outbound_event_payload
from app.webhooks.signing import sign_payload

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
CONSECUTIVE_FAIL_DISABLE = 20
_BACKOFF_BASE_SECONDS = 0.02

_background_tasks: set[asyncio.Task] = set()


def _backoff_seconds(attempt: int) -> float:
    return _BACKOFF_BASE_SECONDS * (2**attempt)


async def _has_subscribers(session: AsyncSession, event: str) -> bool:
    stmt = select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True))
    endpoints = (await session.execute(stmt)).scalars().all()
    return any(event in (e.events or []) for e in endpoints)


async def launch_publish_event(session: AsyncSession, *, event: str, mail_item_id: str) -> None:
    if not await _has_subscribers(session, event):
        return
    task = asyncio.create_task(_publish_event_task(event=event, mail_item_id=mail_item_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _publish_event_task(*, event: str, mail_item_id: str) -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            mail_item = await session.get(MailItem, mail_item_id)
            if mail_item is None:
                return
            await publish_event(session, event=event, mail_item=mail_item, client=None)
        except Exception:  # noqa: BLE001 - never crash the event loop
            logger.exception(
                "webhook publish failed for event=%s mail_item=%s", event, mail_item_id
            )


async def publish_event(
    session: AsyncSession,
    *,
    event: str,
    mail_item: MailItem,
    client: httpx.AsyncClient | None = None,
) -> None:
    stmt = select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True))
    endpoints = (await session.execute(stmt)).scalars().all()
    targets = [e for e in endpoints if event in (e.events or [])]
    if not targets:
        return

    payload = await build_event_payload(session, event=event, mail_item=mail_item)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    for endpoint in targets:
        await deliver_to_endpoint(session, endpoint, body=body, event=event, client=client)
    await session.commit()


async def launch_publish_outbound_event(
    session: AsyncSession, *, event: str, outbound_item_id: str
) -> None:
    if not await _has_subscribers(session, event):
        return
    task = asyncio.create_task(
        _publish_outbound_event_task(event=event, outbound_item_id=outbound_item_id)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _publish_outbound_event_task(*, event: str, outbound_item_id: str) -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            outbound_item = await session.get(OutboundItem, outbound_item_id)
            if outbound_item is None:
                return
            await publish_outbound_event(
                session, event=event, outbound_item=outbound_item, client=None
            )
        except Exception:  # noqa: BLE001 - never crash the event loop
            logger.exception(
                "webhook publish failed for event=%s outbound_item=%s", event, outbound_item_id
            )


async def publish_outbound_event(
    session: AsyncSession,
    *,
    event: str,
    outbound_item: OutboundItem,
    client: httpx.AsyncClient | None = None,
) -> None:
    stmt = select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True))
    endpoints = (await session.execute(stmt)).scalars().all()
    targets = [e for e in endpoints if event in (e.events or [])]
    if not targets:
        return

    payload = await build_outbound_event_payload(session, event=event, outbound_item=outbound_item)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    for endpoint in targets:
        await deliver_to_endpoint(session, endpoint, body=body, event=event, client=client)
    await session.commit()


async def deliver_to_endpoint(
    session: AsyncSession,
    endpoint: WebhookEndpoint,
    *,
    body: str,
    event: str,
    client: httpx.AsyncClient | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> bool:
    headers = {
        "Content-Type": "application/json",
        "X-OpenMailroom-Signature": sign_payload(endpoint.secret, body),
        "X-OpenMailroom-Event": event,
    }
    ok = False
    last_error: str | None = None
    for attempt in range(max_attempts):
        try:
            check_base_url_allowed(
                endpoint.url, allow_private_network=endpoint.allow_private_network
            )
        except UnsafeBaseUrlError as exc:
            last_error = f"SSRF re-check failed: {exc}"
            break
        try:
            resp = await send_http(
                "POST", endpoint.url, content=body, headers=headers, client=client
            )
            if 200 <= resp.status_code < 300:
                ok = True
                break
            last_error = f"HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        if attempt < max_attempts - 1:
            await asyncio.sleep(_backoff_seconds(attempt))

    if ok:
        endpoint.failure_count = 0
        endpoint.last_success_at = datetime.now(timezone.utc)
    else:
        endpoint.failure_count += 1
        if endpoint.failure_count >= CONSECUTIVE_FAIL_DISABLE and endpoint.is_active:
            endpoint.is_active = False
            await alert_admin(
                session,
                kind="webhook_disabled",
                message=(
                    f"Webhook endpoint '{endpoint.name}' ({endpoint.url}) was auto-disabled "
                    f"after {endpoint.failure_count} consecutive delivery failures."
                ),
                meta={"webhook_endpoint_id": endpoint.id, "last_error": last_error},
            )
    await session.flush()
    return ok


async def send_test_delivery(
    endpoint: WebhookEndpoint,
    *,
    body: str,
    event: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-OpenMailroom-Signature": sign_payload(endpoint.secret, body),
        "X-OpenMailroom-Event": event,
    }
    sent_at = datetime.now(timezone.utc)

    try:
        check_base_url_allowed(endpoint.url, allow_private_network=endpoint.allow_private_network)
    except UnsafeBaseUrlError as exc:
        return {
            "success": False,
            "status_code": None,
            "message": f"SSRF re-check failed: {exc}",
            "sent_at": sent_at.isoformat(),
        }

    try:
        resp = await send_http("POST", endpoint.url, content=body, headers=headers, client=client)
    except httpx.HTTPError as exc:
        return {
            "success": False,
            "status_code": None,
            "message": str(exc),
            "sent_at": sent_at.isoformat(),
        }

    success = 200 <= resp.status_code < 300
    message = None if success else f"HTTP {resp.status_code} {resp.text[:300]}"
    return {
        "success": success,
        "status_code": resp.status_code,
        "message": message,
        "sent_at": sent_at.isoformat(),
    }
