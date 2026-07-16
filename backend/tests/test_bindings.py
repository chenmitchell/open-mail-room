"""Employee self-service notification bindings + the LINE/Telegram inbound
webhook completion flow (05-NOTIFICATIONS.md section 3): binding codes
(issue/expire/wrong-code), LINE signature verification, direct-bind SSRF
rejection."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from app.models.employee import Employee
from app.models.enums import NotificationChannel, UserRole
from app.models.notification_binding import NotificationBinding
from app.models.notification_binding_code import NotificationBindingCode
from app.notify.binding_codes import MAX_FAILED_ATTEMPTS
from app.notify.settings_store import set_setting
from tests._helpers import create_user, login


async def _employee_user(db_session, *, email="staff@example.com", name="王小明") -> Employee:
    user = await create_user(db_session, email=email, role=UserRole.employee)
    emp = Employee(name=name, aliases=[], user_id=user.id)
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


async def test_start_binding_requires_linked_employee(client, db_session):
    await create_user(db_session, email="noemp@example.com", role=UserRole.employee)
    await login(client, email="noemp@example.com")

    resp = await client.post("/api/v1/me/bindings/line/start")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "EMPLOYEE_NOT_FOUND"


async def test_start_binding_issues_6_digit_code(client, db_session):
    await _employee_user(db_session)
    await login(client, email="staff@example.com")

    resp = await client.post("/api/v1/me/bindings/line/start")
    assert resp.status_code == 201
    body = resp.json()["data"]
    assert len(body["code"]) == 6
    assert body["code"].isdigit()
    assert body["channel"] == "line"


async def test_start_binding_rejects_direct_channels(client, db_session):
    await _employee_user(db_session)
    await login(client, email="staff@example.com")

    resp = await client.post("/api/v1/me/bindings/email/start")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BINDING_CHANNEL_UNSUPPORTED"


def _line_signature(secret: str, body: bytes) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


async def test_line_webhook_rejects_bad_signature(client, db_session):
    await set_setting(db_session, "notify.line.channel_secret", "linesecret", secret=True)
    resp = await client.post(
        "/api/v1/webhooks/line",
        content=b'{"events": []}',
        headers={"X-Line-Signature": "totally-wrong", "Content-Type": "application/json"},
    )
    assert resp.status_code == 403


async def test_line_webhook_rejects_when_no_secret_configured(client, db_session):
    resp = await client.post(
        "/api/v1/webhooks/line",
        content=b'{"events": []}',
        headers={"X-Line-Signature": "anything"},
    )
    assert resp.status_code == 403


async def test_line_webhook_binds_on_valid_signature_and_matching_code(client, db_session):
    emp = await _employee_user(db_session)
    await set_setting(db_session, "notify.line.channel_secret", "linesecret", secret=True)

    code_row = NotificationBindingCode(
        employee_id=emp.id,
        channel=NotificationChannel.line,
        code="123456",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db_session.add(code_row)
    await db_session.commit()

    payload = {
        "events": [
            {
                "type": "message",
                "message": {"type": "text", "text": "123456"},
                "source": {"userId": "Uabc123"},
            }
        ]
    }
    body = json.dumps(payload).encode()
    sig = _line_signature("linesecret", body)

    resp = await client.post(
        "/api/v1/webhooks/line",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["bound"] == 1

    from sqlalchemy import select

    result = await db_session.execute(
        select(NotificationBinding).where(NotificationBinding.employee_id == emp.id)
    )
    bindings = result.scalars().all()
    assert len(bindings) == 1
    assert bindings[0].channel == NotificationChannel.line
    assert bindings[0].address == "Uabc123"

    refreshed_code = await db_session.get(NotificationBindingCode, code_row.id)
    await db_session.refresh(refreshed_code)
    assert refreshed_code.consumed_at is not None


async def test_line_webhook_wrong_code_does_not_bind(client, db_session):
    emp = await _employee_user(db_session)
    await set_setting(db_session, "notify.line.channel_secret", "linesecret", secret=True)

    code_row = NotificationBindingCode(
        employee_id=emp.id,
        channel=NotificationChannel.line,
        code="111111",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db_session.add(code_row)
    await db_session.commit()

    payload = {
        "events": [
            {
                "type": "message",
                "message": {"type": "text", "text": "999999"},
                "source": {"userId": "Uxyz"},
            }
        ]
    }
    body = json.dumps(payload).encode()
    sig = _line_signature("linesecret", body)

    resp = await client.post(
        "/api/v1/webhooks/line",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["bound"] == 0

    from sqlalchemy import select

    result = await db_session.execute(
        select(NotificationBinding).where(NotificationBinding.employee_id == emp.id)
    )
    assert result.scalars().all() == []


async def test_line_webhook_expired_code_does_not_bind(client, db_session):
    emp = await _employee_user(db_session)
    await set_setting(db_session, "notify.line.channel_secret", "linesecret", secret=True)

    code_row = NotificationBindingCode(
        employee_id=emp.id,
        channel=NotificationChannel.line,
        code="222222",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # already expired
    )
    db_session.add(code_row)
    await db_session.commit()

    payload = {
        "events": [
            {
                "type": "message",
                "message": {"type": "text", "text": "222222"},
                "source": {"userId": "Uexpired"},
            }
        ]
    }
    body = json.dumps(payload).encode()
    sig = _line_signature("linesecret", body)

    resp = await client.post(
        "/api/v1/webhooks/line",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["bound"] == 0


async def test_telegram_webhook_binds_via_start_command(client, db_session):
    emp = await _employee_user(db_session)
    await set_setting(db_session, "notify.telegram.webhook_secret", "tgsecret", secret=True)
    code_row = NotificationBindingCode(
        employee_id=emp.id,
        channel=NotificationChannel.telegram,
        code="654321",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db_session.add(code_row)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/webhooks/telegram",
        json={"message": {"text": "/start 654321", "chat": {"id": 999888}}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "tgsecret"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["bound"] is True

    from sqlalchemy import select

    result = await db_session.execute(
        select(NotificationBinding).where(NotificationBinding.employee_id == emp.id)
    )
    bindings = result.scalars().all()
    assert len(bindings) == 1
    assert bindings[0].address == "999888"


async def test_telegram_webhook_rejects_when_no_secret_configured(client, db_session):
    """M3-R1 blocking #1: fail-closed like LINE -- an unconfigured secret must
    never mean "accept anything". Previously this let anyone hit the webhook
    directly (bypassing Telegram's own servers entirely) and brute-force
    binding codes with no signature/secret check at all."""
    resp = await client.post(
        "/api/v1/webhooks/telegram",
        json={"message": {"text": "/start 000000", "chat": {"id": 1}}},
    )
    assert resp.status_code == 403


async def test_telegram_webhook_rejects_wrong_secret(client, db_session):
    await set_setting(db_session, "notify.telegram.webhook_secret", "tgsecret", secret=True)
    resp = await client.post(
        "/api/v1/webhooks/telegram",
        json={"message": {"text": "/start 000000", "chat": {"id": 1}}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "totally-wrong"},
    )
    assert resp.status_code == 403


async def test_webhook_endpoints_rate_limited_per_ip(client, db_session):
    """M3-R1 blocking #1/#2: a per-IP request counter on the inbound channel
    webhooks, independent of the per-code failed-attempt budget below."""
    for _ in range(30):
        resp = await client.post(
            "/api/v1/webhooks/line",
            content=b'{"events": []}',
            headers={"X-Line-Signature": "anything"},
        )
        assert resp.status_code == 403

    resp = await client.post(
        "/api/v1/webhooks/line",
        content=b'{"events": []}',
        headers={"X-Line-Signature": "anything"},
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "WEBHOOK_RATE_LIMITED"


async def test_binding_code_invalidated_after_max_failed_attempts(client, db_session):
    """M3-R1 blocking #2: a real outstanding code stops matching once the
    shared wrong-guess budget for its channel is exhausted -- otherwise the
    10^6 code space has no attempt cap at all."""
    emp = await _employee_user(db_session)
    await set_setting(db_session, "notify.line.channel_secret", "linesecret", secret=True)

    code_row = NotificationBindingCode(
        employee_id=emp.id,
        channel=NotificationChannel.line,
        code="777777",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db_session.add(code_row)
    await db_session.commit()

    def _wrong_guess_payload(guess: str) -> bytes:
        return json.dumps(
            {
                "events": [
                    {
                        "type": "message",
                        "message": {"type": "text", "text": guess},
                        "source": {"userId": f"Uattacker-{guess}"},
                    }
                ]
            }
        ).encode()

    for i in range(MAX_FAILED_ATTEMPTS):
        body = _wrong_guess_payload(f"00000{i}")
        sig = _line_signature("linesecret", body)
        resp = await client.post(
            "/api/v1/webhooks/line",
            content=body,
            headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["bound"] == 0

    refreshed_code = await db_session.get(NotificationBindingCode, code_row.id)
    await db_session.refresh(refreshed_code)
    assert refreshed_code.failed_attempts == MAX_FAILED_ATTEMPTS

    # The *correct* code no longer binds -- it was invalidated by the shared
    # attempt budget being exhausted, even though it never expired.
    body = json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "message": {"type": "text", "text": "777777"},
                    "source": {"userId": "Ulegituser"},
                }
            ]
        }
    ).encode()
    sig = _line_signature("linesecret", body)
    resp = await client.post(
        "/api/v1/webhooks/line",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["bound"] == 0

    from sqlalchemy import select

    result = await db_session.execute(
        select(NotificationBinding).where(NotificationBinding.employee_id == emp.id)
    )
    assert result.scalars().all() == []


async def test_direct_bind_email_success(client, db_session):
    """M3-R1 blocking #4: `channel` is a path parameter
    (POST /me/bindings/{channel}), matching 03-API-SPEC.md section 2 and what
    frontend/src/api/bindings.ts actually sends -- the old
    `POST /me/bindings` + body `{channel, address}` shape 404'd against the
    real frontend."""
    await _employee_user(db_session)
    await login(client, email="staff@example.com")

    resp = await client.post("/api/v1/me/bindings/email", json={"address": "me@example.com"})
    assert resp.status_code == 201
    body = resp.json()["data"]
    assert body["channel"] == "email"
    assert body["is_verified"] is True
    # M3-R1 suggestion (adopted): address is masked, never echoed back raw.
    assert body["address"] != "me@example.com"
    assert body["address"].startswith("me")


async def test_direct_bind_old_body_shaped_channel_no_longer_accepted(client, db_session):
    """The pre-fix contract (`POST /me/bindings` with `channel` in the JSON
    body) must no longer be accepted -- `GET /me/bindings` still exists at
    that exact path (listing), so plain routing rules make this a 405
    (method not allowed at that path), not a 404; either way it must not be
    a 201 create. Guards against silently reintroducing the shape the
    frontend 404'd against before this blocking fix."""
    await _employee_user(db_session)
    await login(client, email="staff@example.com")

    resp = await client.post(
        "/api/v1/me/bindings", json={"channel": "email", "address": "me@example.com"}
    )
    assert resp.status_code in (404, 405)


async def test_direct_bind_email_rejects_invalid_address(client, db_session):
    await _employee_user(db_session)
    await login(client, email="staff@example.com")

    resp = await client.post("/api/v1/me/bindings/email", json={"address": "not-an-email"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BINDING_ADDRESS_INVALID"


async def test_direct_bind_webhook_rejects_private_network_url(client, db_session):
    await _employee_user(db_session)
    await login(client, email="staff@example.com")

    resp = await client.post(
        "/api/v1/me/bindings/webhook",
        json={"address": "https://169.254.169.254/steal"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BINDING_ADDRESS_UNSAFE"


async def test_direct_bind_webhook_rejects_plain_http(client, db_session):
    await _employee_user(db_session)
    await login(client, email="staff@example.com")

    resp = await client.post(
        "/api/v1/me/bindings/webhook",
        json={"address": "http://example.com/hook"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BINDING_ADDRESS_UNSAFE"


async def test_direct_bind_webhook_accepts_https_public_url(client, db_session):
    await _employee_user(db_session)
    await login(client, email="staff@example.com")

    resp = await client.post(
        "/api/v1/me/bindings/webhook",
        json={"address": "https://example.com/hook"},
    )
    assert resp.status_code == 201


async def test_direct_bind_line_rejected_must_use_start_flow(client, db_session):
    await _employee_user(db_session)
    await login(client, email="staff@example.com")

    resp = await client.post("/api/v1/me/bindings/line", json={"address": "U1"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BINDING_CHANNEL_UNSUPPORTED"


async def test_list_and_delete_own_binding(client, db_session):
    emp = await _employee_user(db_session)
    await login(client, email="staff@example.com")

    binding = NotificationBinding(
        employee_id=emp.id, channel=NotificationChannel.email, address="a@b.com"
    )
    db_session.add(binding)
    await db_session.commit()
    await db_session.refresh(binding)

    resp = await client.get("/api/v1/me/bindings")
    assert resp.status_code == 200
    listed = resp.json()["data"]
    assert len(listed) == 1
    assert listed[0]["address"] != "a@b.com"

    del_resp = await client.delete(f"/api/v1/me/bindings/{binding.id}")
    assert del_resp.status_code == 200

    resp2 = await client.get("/api/v1/me/bindings")
    assert resp2.json()["data"] == []


async def test_delete_binding_belonging_to_someone_else_forbidden(client, db_session):
    other_emp = Employee(name="別人", aliases=[])
    db_session.add(other_emp)
    await db_session.commit()
    await db_session.refresh(other_emp)
    other_binding = NotificationBinding(
        employee_id=other_emp.id, channel=NotificationChannel.email, address="other@example.com"
    )
    db_session.add(other_binding)
    await db_session.commit()
    await db_session.refresh(other_binding)

    await _employee_user(db_session)
    await login(client, email="staff@example.com")

    resp = await client.delete(f"/api/v1/me/bindings/{other_binding.id}")
    assert resp.status_code == 404
