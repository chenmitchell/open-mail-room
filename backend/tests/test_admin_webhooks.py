"""Admin outbound webhook subscriptions CRUD + test-send + SSRF rejection
(03-API-SPEC.md section 2 "管理", section 3 "對外 Webhook")."""

from __future__ import annotations

import httpx

from app.models.enums import UserRole
from app.models.webhook_endpoint import WebhookEndpoint
from tests._helpers import login_as


async def test_create_webhook_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post(
        "/api/v1/admin/webhooks",
        json={"name": "x", "url": "https://example.com/hook", "events": ["item.received"]},
    )
    assert resp.status_code == 403


async def test_create_webhook_success_returns_secret_once(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/webhooks",
        json={"name": "erp-sync", "url": "https://example.com/hook", "events": ["item.received"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert "secret" in body and len(body["secret"]) > 10
    assert body["failure_count"] == 0
    assert body["is_active"] is True


async def test_create_webhook_rejects_unknown_event(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/webhooks",
        json={"name": "x", "url": "https://example.com/hook", "events": ["item.made_up"]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "WEBHOOK_EVENT_UNKNOWN"


async def test_create_webhook_rejects_private_network_url(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/webhooks",
        json={
            "name": "x",
            "url": "https://192.168.1.5/hook",
            "events": ["item.received"],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "WEBHOOK_UNSAFE_URL"


async def test_create_webhook_allows_private_network_with_opt_in(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/webhooks",
        json={
            "name": "internal",
            "url": "http://192.168.1.5/hook",
            "events": ["item.received"],
            "allow_private_network": True,
        },
    )
    assert resp.status_code == 201, resp.text


async def test_create_webhook_rejects_plain_http_without_opt_in(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/webhooks",
        json={"name": "x", "url": "http://example.com/hook", "events": ["item.received"]},
    )
    assert resp.status_code == 400


async def test_list_and_patch_webhook(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    created = (
        await client.post(
            "/api/v1/admin/webhooks",
            json={"name": "x", "url": "https://example.com/hook", "events": ["item.received"]},
        )
    ).json()["data"]

    list_resp = await client.get("/api/v1/admin/webhooks")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]) == 1
    # Listing must never re-expose the secret.
    assert "secret" not in list_resp.json()["data"][0]

    patch_resp = await client.patch(
        f"/api/v1/admin/webhooks/{created['id']}", json={"is_active": False}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["is_active"] is False


async def test_patch_webhook_reject_unsafe_url(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    created = (
        await client.post(
            "/api/v1/admin/webhooks",
            json={"name": "x", "url": "https://example.com/hook", "events": ["item.received"]},
        )
    ).json()["data"]

    resp = await client.patch(
        f"/api/v1/admin/webhooks/{created['id']}", json={"url": "https://10.0.0.5/hook"}
    )
    assert resp.status_code == 400


async def test_webhook_test_endpoint_does_not_affect_failure_count(client, db_session, monkeypatch):
    await login_as(client, db_session, role=UserRole.admin)
    created = (
        await client.post(
            "/api/v1/admin/webhooks",
            json={"name": "x", "url": "https://example.com/hook", "events": ["item.received"]},
        )
    ).json()["data"]

    async def _fake_send_http(method, url, **kwargs):
        return httpx.Response(500)

    # `send_test_delivery` (called by the /test endpoint with no injected
    # client) resolves `send_http` from app.webhooks.publisher's own module
    # namespace (bound there by `from app.notify.http import send_http`), so
    # that's the name that needs patching to keep this test off the network.
    import app.webhooks.publisher as publisher_module

    monkeypatch.setattr(publisher_module, "send_http", _fake_send_http)

    resp = await client.post(f"/api/v1/admin/webhooks/{created['id']}/test")
    assert resp.status_code == 200
    # M3-R1 blocking #6: {success, status_code, message, sent_at}, not {ok}.
    body = resp.json()["data"]
    assert body["success"] is False
    assert body["status_code"] == 500
    assert body["message"]
    assert body["sent_at"]

    endpoint = await db_session.get(WebhookEndpoint, created["id"])
    await db_session.refresh(endpoint)
    assert endpoint.failure_count == 0
    assert endpoint.is_active is True
