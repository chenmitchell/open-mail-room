"""Admin-managed outbound webhook subscriptions (03-API-SPEC.md section 2
"管理": `GET|POST|PATCH /admin/webhooks`, `POST /admin/webhooks/{id}/test`).

`url` is SSRF-checked the same way as `ai_provider_configs.base_url`
(app/security/ssrf.py) -- `allow_private_network` is the documented opt-in
for a deployment that genuinely wants to push events to an internal-network
receiver (07-SECURITY.md section 5: "除非 admin 明示放行"). The signing
`secret` is generated server-side and shown once on create (never readable
again, same UX as an API key), then stored the normal `Encrypted` way (it's
a real column, not a `settings` row).
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok
from app.db import get_session
from app.models.enums import UserRole
from app.models.user import User
from app.models.webhook_endpoint import WebhookEndpoint
from app.security.csrf import require_csrf
from app.security.rbac import require_role
from app.security.ssrf import UnsafeBaseUrlError, check_base_url_allowed
from app.services.audit import record_audit
from app.webhooks.events import ALL_EVENTS
from app.webhooks.publisher import send_test_delivery

router = APIRouter(
    prefix="/admin/webhooks", tags=["admin_webhooks"], dependencies=[Depends(require_csrf)]
)

ADMIN_ONLY = (UserRole.admin,)


def _serialize(endpoint: WebhookEndpoint) -> dict[str, Any]:
    return {
        "id": endpoint.id,
        "name": endpoint.name,
        "url": endpoint.url,
        "events": endpoint.events,
        "is_active": endpoint.is_active,
        "allow_private_network": endpoint.allow_private_network,
        "last_success_at": endpoint.last_success_at.isoformat()
        if endpoint.last_success_at
        else None,
        "failure_count": endpoint.failure_count,
        "created_at": endpoint.created_at.isoformat(),
        "updated_at": endpoint.updated_at.isoformat(),
    }


def _unsafe_url(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "WEBHOOK_UNSAFE_URL", "message": message})


def _validate_events(events: list[str]) -> None:
    unknown = [e for e in events if e not in ALL_EVENTS]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={"code": "WEBHOOK_EVENT_UNKNOWN", "message": f"Unknown event(s): {unknown}"},
        )


class WebhookCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2048)
    events: list[str] = Field(min_length=1)
    is_active: bool = True
    allow_private_network: bool = False


class WebhookUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    url: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None
    allow_private_network: bool | None = None


async def _get_or_404(session: AsyncSession, endpoint_id: str) -> WebhookEndpoint:
    endpoint = await session.get(WebhookEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "Webhook endpoint not found"}
        )
    return endpoint


@router.get("")
async def list_webhooks(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*ADMIN_ONLY)),
):
    rows = (
        (await session.execute(select(WebhookEndpoint).order_by(WebhookEndpoint.created_at.asc())))
        .scalars()
        .all()
    )
    return ok([_serialize(e) for e in rows])


@router.get("/{endpoint_id}")
async def get_webhook(
    endpoint_id: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*ADMIN_ONLY)),
):
    endpoint = await _get_or_404(session, endpoint_id)
    return ok(_serialize(endpoint))


@router.post("", status_code=201)
async def create_webhook(
    payload: WebhookCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*ADMIN_ONLY)),
):
    _validate_events(payload.events)
    try:
        check_base_url_allowed(payload.url, allow_private_network=payload.allow_private_network)
    except UnsafeBaseUrlError as exc:
        raise _unsafe_url(str(exc)) from exc
    if not payload.allow_private_network and not payload.url.lower().startswith("https://"):
        raise _unsafe_url("Webhook URLs must use https:// unless allow_private_network is set")

    secret = secrets.token_urlsafe(32)
    endpoint = WebhookEndpoint(
        name=payload.name,
        url=payload.url,
        secret=secret,
        events=list(payload.events),
        is_active=payload.is_active,
        allow_private_network=payload.allow_private_network,
    )
    session.add(endpoint)
    await session.flush()

    await record_audit(
        session,
        request=request,
        actor=user,
        action="webhook_endpoint.create",
        target_type="webhook_endpoint",
        target_id=endpoint.id,
        diff={"after": _serialize(endpoint)},
    )
    await session.commit()
    await session.refresh(endpoint)
    # Secret is write-only from here on -- shown exactly once, on creation.
    return ok({**_serialize(endpoint), "secret": secret})


@router.patch("/{endpoint_id}")
async def update_webhook(
    endpoint_id: str,
    payload: WebhookUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*ADMIN_ONLY)),
):
    endpoint = await _get_or_404(session, endpoint_id)
    before = _serialize(endpoint)

    updates = payload.model_dump(exclude_unset=True)
    if "events" in updates and updates["events"] is not None:
        _validate_events(updates["events"])
    for field, value in updates.items():
        setattr(endpoint, field, value)

    try:
        check_base_url_allowed(endpoint.url, allow_private_network=endpoint.allow_private_network)
    except UnsafeBaseUrlError as exc:
        raise _unsafe_url(str(exc)) from exc
    if not endpoint.allow_private_network and not endpoint.url.lower().startswith("https://"):
        raise _unsafe_url("Webhook URLs must use https:// unless allow_private_network is set")

    await session.flush()
    after = _serialize(endpoint)

    await record_audit(
        session,
        request=request,
        actor=user,
        action="webhook_endpoint.update",
        target_type="webhook_endpoint",
        target_id=endpoint.id,
        diff={"before": before, "after": after},
    )
    await session.commit()
    await session.refresh(endpoint)
    return ok(_serialize(endpoint))


@router.post("/{endpoint_id}/test")
async def test_webhook(
    endpoint_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*ADMIN_ONLY)),
):
    endpoint = await _get_or_404(session, endpoint_id)
    payload = {
        "event": "test",
        "id": "evt_test",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": {"message": "This is a test delivery from OpenMailroom"},
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    # A manual "test" ping is a single attempt (no retry/backoff) and never
    # counts toward the auto-disable failure streak -- snapshot/restore
    # failure_count/is_active around the call (send_test_delivery itself
    # never touches them, but this stays as a defensive belt-and-braces).
    before_failures = endpoint.failure_count
    before_active = endpoint.is_active
    result = await send_test_delivery(endpoint, body=body, event="test")
    endpoint.failure_count = before_failures
    endpoint.is_active = before_active
    await session.flush()

    await record_audit(
        session,
        request=request,
        actor=user,
        action="webhook_endpoint.test",
        target_type="webhook_endpoint",
        target_id=endpoint.id,
        diff={"success": result["success"], "status_code": result["status_code"]},
    )
    await session.commit()
    # M3-R1 blocking #6: shape must match src/types/api.ts `WebhookTestResult`
    # ({success, status_code, message, sent_at}), not the old bare {ok}.
    return ok(result)
