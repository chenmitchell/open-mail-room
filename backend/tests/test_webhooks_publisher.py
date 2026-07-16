"""Outbound webhook publisher: HMAC signing (recomputable by a receiver),
retry/backoff, and auto-disable after 20 consecutive failures
(03-API-SPEC.md section 3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.enums import MailStatus, MailType, Refrigeration
from app.models.mail_item import MailItem
from app.models.webhook_endpoint import WebhookEndpoint
from app.webhooks.publisher import (
    CONSECUTIVE_FAIL_DISABLE,
    deliver_to_endpoint,
    publish_event,
    send_test_delivery,
)
from app.webhooks.signing import sign_payload, verify_signature


def test_sign_and_verify_roundtrip():
    body = json.dumps({"a": 1}, sort_keys=True)
    header = sign_payload("s3cret", body, timestamp=1_700_000_000)
    assert header.startswith("t=1700000000,v1=")
    assert verify_signature("s3cret", body, header, now=1_700_000_010) is True


def test_verify_signature_rejects_tampered_body():
    body = json.dumps({"a": 1}, sort_keys=True)
    header = sign_payload("s3cret", body)
    assert verify_signature("s3cret", '{"a":2}', header) is False


def test_verify_signature_rejects_wrong_secret():
    body = "hello"
    header = sign_payload("s3cret", body)
    assert verify_signature("different-secret", body, header) is False


def test_verify_signature_rejects_outside_replay_window():
    body = "hello"
    header = sign_payload("s3cret", body, timestamp=1_700_000_000)
    # 10 minutes later -- outside the default 5-minute window.
    assert verify_signature("s3cret", body, header, now=1_700_000_000 + 600) is False


def test_verify_signature_rejects_missing_or_malformed_header():
    assert verify_signature("s3cret", "hello", None) is False
    assert verify_signature("s3cret", "hello", "garbage") is False
    assert verify_signature("s3cret", "hello", "t=notanumber,v1=abc") is False


async def _make_item(db_session) -> MailItem:
    item = MailItem(
        item_no="IN-TEST-WEBHOOK",
        direction="inbound",
        mail_type=MailType.parcel,
        recipient_name_raw="測試",
        received_at=datetime.now(timezone.utc),
        status=MailStatus.received,
        refrigeration=Refrigeration.none,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _make_endpoint(db_session, *, events, failure_count=0, is_active=True) -> WebhookEndpoint:
    endpoint = WebhookEndpoint(
        name="test-endpoint",
        url="https://example.com/hook",
        secret="whsecret",
        events=events,
        is_active=is_active,
        failure_count=failure_count,
    )
    db_session.add(endpoint)
    await db_session.commit()
    await db_session.refresh(endpoint)
    return endpoint


@pytest.mark.asyncio
async def test_publish_event_delivers_signed_payload_to_subscribed_endpoint(db_session):
    item = await _make_item(db_session)
    endpoint = await _make_endpoint(db_session, events=["item.received"])

    received = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["sig"] = request.headers.get("x-openmailroom-signature")
        received["body"] = request.content.decode()
        received["event_header"] = request.headers.get("x-openmailroom-event")
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await publish_event(db_session, event="item.received", mail_item=item, client=client)

    payload = json.loads(received["body"])
    assert payload["event"] == "item.received"
    assert payload["data"]["item_no"] == item.item_no
    assert verify_signature("whsecret", received["body"], received["sig"]) is True

    refreshed = await db_session.get(WebhookEndpoint, endpoint.id)
    await db_session.refresh(refreshed)
    assert refreshed.failure_count == 0
    assert refreshed.last_success_at is not None


@pytest.mark.asyncio
async def test_publish_event_ignores_endpoints_not_subscribed(db_session):
    item = await _make_item(db_session)
    await _make_endpoint(db_session, events=["item.picked_up"])

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await publish_event(db_session, event="item.received", mail_item=item, client=client)
    assert calls == []


@pytest.mark.asyncio
async def test_publish_event_hides_sender_for_confidential_items(db_session):
    item = await _make_item(db_session)
    item.is_confidential = True
    item.sender_org = "Secret Co"
    await db_session.commit()
    await _make_endpoint(db_session, events=["item.received"])

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await publish_event(db_session, event="item.received", mail_item=item, client=client)

    payload = json.loads(captured["body"])
    assert payload["data"]["confidential"] is True
    assert "sender" not in payload["data"]


@pytest.mark.asyncio
async def test_deliver_to_endpoint_retries_then_succeeds(db_session):
    item = await _make_item(db_session)  # noqa: F841 - keeps FK-less test simple
    endpoint = await _make_endpoint(db_session, events=["item.received"])

    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(500)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ok = await deliver_to_endpoint(db_session, endpoint, body="{}", event="test", client=client)
    assert ok is True
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_deliver_to_endpoint_auto_disables_after_20_consecutive_failures(db_session):
    endpoint = await _make_endpoint(
        db_session, events=["item.received"], failure_count=CONSECUTIVE_FAIL_DISABLE - 1
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ok = await deliver_to_endpoint(
        db_session, endpoint, body="{}", event="test", client=client, max_attempts=1
    )
    assert ok is False

    refreshed = await db_session.get(WebhookEndpoint, endpoint.id)
    await db_session.refresh(refreshed)
    assert refreshed.failure_count == CONSECUTIVE_FAIL_DISABLE
    assert refreshed.is_active is False

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "admin_alert.webhook_disabled")
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_deliver_to_endpoint_rechecks_ssrf_before_each_attempt(db_session):
    """M3-R1 suggestion (adopted): re-run the SSRF check right before
    delivery, not just once at admin create/update time
    (app/api/v1/admin_webhooks.py). Bypasses that create-time check by
    inserting the row directly, simulating a URL that resolved safely when
    configured but now points at a private/reserved address (e.g. DNS
    rebinding) -- delivery must refuse without ever calling send_http."""
    endpoint = WebhookEndpoint(
        name="rebound",
        url="https://169.254.169.254/steal",
        secret="whsecret",
        events=["item.received"],
        is_active=True,
    )
    db_session.add(endpoint)
    await db_session.commit()
    await db_session.refresh(endpoint)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ok = await deliver_to_endpoint(
        db_session, endpoint, body="{}", event="test", client=client, max_attempts=1
    )
    assert ok is False
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_send_test_delivery_shape_and_ssrf_recheck(db_session):
    """M3-R1 blocking #6: the /test endpoint's result shape is
    {success, status_code, message, sent_at} (src/types/api.ts
    `WebhookTestResult`), not `deliver_to_endpoint`'s bare bool."""
    endpoint = await _make_endpoint(db_session, events=["item.received"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await send_test_delivery(endpoint, body="{}", event="test", client=client)
    assert result["success"] is True
    assert result["status_code"] == 200
    assert result["message"] is None
    assert result["sent_at"]

    unsafe_endpoint = WebhookEndpoint(
        name="rebound2",
        url="http://127.0.0.1/admin",
        secret="whsecret2",
        events=["item.received"],
        is_active=True,
    )
    db_session.add(unsafe_endpoint)
    await db_session.commit()
    await db_session.refresh(unsafe_endpoint)

    calls = {"n": 0}

    def handler2(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200)

    client2 = httpx.AsyncClient(transport=httpx.MockTransport(handler2))
    result2 = await send_test_delivery(unsafe_endpoint, body="{}", event="test", client=client2)
    assert result2["success"] is False
    assert result2["status_code"] is None
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_deliver_to_endpoint_success_resets_failure_count(db_session):
    endpoint = await _make_endpoint(db_session, events=["item.received"], failure_count=15)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ok = await deliver_to_endpoint(db_session, endpoint, body="{}", event="test", client=client)
    assert ok is True

    refreshed = await db_session.get(WebhookEndpoint, endpoint.id)
    await db_session.refresh(refreshed)
    assert refreshed.failure_count == 0
