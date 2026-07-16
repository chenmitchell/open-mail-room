"""Per-adapter success/failure unit tests (05-NOTIFICATIONS.md section 2).
Retry/dead-letter behavior across attempts is covered at the worker level in
tests/test_notify_worker.py; these tests exercise a single `.send()` call.
"""

from __future__ import annotations

import smtplib

import httpx
import pytest

from app.notify.adapters.discord import DiscordAdapter
from app.notify.adapters.email import EmailAdapter, SmtpConfig
from app.notify.adapters.line import LineAdapter
from app.notify.adapters.slack import SlackAdapter
from app.notify.adapters.telegram import TelegramAdapter
from app.notify.adapters.webhook import GenericWebhookAdapter
from app.notify.base import RenderedMessage


class _Binding:
    def __init__(self, address: str) -> None:
        self.address = address


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_line_adapter_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer tok123"
        return httpx.Response(200, json={})

    adapter = LineAdapter(channel_access_token="tok123", client=_client_for(handler))
    result = await adapter.send(_Binding("U123"), RenderedMessage(text="hello"))
    assert result.ok is True


@pytest.mark.asyncio
async def test_line_adapter_failure_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="invalid userId")

    adapter = LineAdapter(channel_access_token="tok123", client=_client_for(handler))
    result = await adapter.send(_Binding("bad"), RenderedMessage(text="hello"))
    assert result.ok is False
    assert "400" in result.error


@pytest.mark.asyncio
async def test_line_adapter_missing_token_fails_fast_without_http_call():
    adapter = LineAdapter(channel_access_token="", client=None)
    result = await adapter.send(_Binding("U1"), RenderedMessage(text="hi"))
    assert result.ok is False
    assert "not configured" in result.error


@pytest.mark.asyncio
async def test_telegram_adapter_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    adapter = TelegramAdapter(bot_token="tok", client=_client_for(handler))
    result = await adapter.send(_Binding("12345"), RenderedMessage(text="hello"))
    assert result.ok is True


@pytest.mark.asyncio
async def test_telegram_adapter_api_level_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "description": "chat not found"})

    adapter = TelegramAdapter(bot_token="tok", client=_client_for(handler))
    result = await adapter.send(_Binding("nope"), RenderedMessage(text="hello"))
    assert result.ok is False
    assert "chat not found" in result.error


@pytest.mark.asyncio
async def test_slack_adapter_success_and_failure():
    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    adapter = SlackAdapter(client=_client_for(ok_handler))
    result = await adapter.send(_Binding("https://hooks.slack.com/x"), RenderedMessage(text="hi"))
    assert result.ok is True

    def fail_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="no_service")

    adapter2 = SlackAdapter(client=_client_for(fail_handler))
    result2 = await adapter2.send(_Binding("https://hooks.slack.com/x"), RenderedMessage(text="hi"))
    assert result2.ok is False


@pytest.mark.asyncio
async def test_discord_adapter_success_204():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    adapter = DiscordAdapter(client=_client_for(handler))
    result = await adapter.send(
        _Binding("https://discord.com/api/webhooks/x"), RenderedMessage(text="hi")
    )
    assert result.ok is True


@pytest.mark.asyncio
async def test_discord_adapter_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="oops")

    adapter = DiscordAdapter(client=_client_for(handler))
    result = await adapter.send(
        _Binding("https://discord.com/api/webhooks/x"), RenderedMessage(text="hi")
    )
    assert result.ok is False


@pytest.mark.asyncio
async def test_generic_webhook_adapter_signs_and_succeeds():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["sig"] = request.headers.get("x-openmailroom-signature")
        seen["body"] = request.content
        return httpx.Response(200)

    adapter = GenericWebhookAdapter(hmac_secret="s3cr3t", client=_client_for(handler))
    result = await adapter.send(_Binding("https://example.com/hook"), RenderedMessage(text="hi"))
    assert result.ok is True
    assert seen["sig"] is not None and seen["sig"].startswith("t=")


@pytest.mark.asyncio
async def test_generic_webhook_adapter_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    adapter = GenericWebhookAdapter(hmac_secret="s3cr3t", client=_client_for(handler))
    result = await adapter.send(_Binding("https://example.com/hook"), RenderedMessage(text="hi"))
    assert result.ok is False


@pytest.mark.asyncio
async def test_generic_webhook_adapter_rechecks_ssrf_before_send():
    """M3-R1 suggestion (adopted): the SSRF check runs again right before
    delivery, not just at bind time -- a binding whose address is (or has
    been DNS-rebound to) a private/reserved address must never actually
    reach send_http. A literal private IP needs no DNS to trip this, same as
    tests/test_ssrf_unit.py."""
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200)

    adapter = GenericWebhookAdapter(hmac_secret="s3cr3t", client=_client_for(handler))
    result = await adapter.send(
        _Binding("https://169.254.169.254/steal"), RenderedMessage(text="hi")
    )
    assert result.ok is False
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_slack_adapter_rechecks_ssrf_before_send():
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200)

    adapter = SlackAdapter(client=_client_for(handler))
    result = await adapter.send(_Binding("https://10.0.0.5/hook"), RenderedMessage(text="hi"))
    assert result.ok is False
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_discord_adapter_rechecks_ssrf_before_send():
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200)

    adapter = DiscordAdapter(client=_client_for(handler))
    result = await adapter.send(_Binding("https://192.168.1.5/hook"), RenderedMessage(text="hi"))
    assert result.ok is False
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_email_adapter_success(monkeypatch):
    calls = []

    class _FakeSmtp:
        def __init__(self, host, port, timeout=10):
            calls.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            calls.append("starttls")

        def login(self, user, pw):
            calls.append(("login", user, pw))

        def send_message(self, msg):
            calls.append(("sent", msg["To"], msg["Subject"]))

    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)

    cfg = SmtpConfig(host="smtp.example.com", port=587, use_tls=True, from_addr="noreply@x.com")
    adapter = EmailAdapter(config=cfg)
    result = await adapter.send(_Binding("emp@example.com"), RenderedMessage(text="hi there"))
    assert result.ok is True
    assert ("sent", "emp@example.com", "Open Mail Room 通知") in calls


@pytest.mark.asyncio
async def test_email_adapter_failure(monkeypatch):
    class _FailingSmtp:
        def __init__(self, host, port, timeout=10):
            pass

        def __enter__(self):
            raise smtplib.SMTPConnectError(421, "cannot connect")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(smtplib, "SMTP", _FailingSmtp)

    cfg = SmtpConfig(host="smtp.example.com")
    adapter = EmailAdapter(config=cfg)
    result = await adapter.send(_Binding("emp@example.com"), RenderedMessage(text="hi"))
    assert result.ok is False


@pytest.mark.asyncio
async def test_email_adapter_no_host_configured():
    adapter = EmailAdapter(config=SmtpConfig(host=""))
    result = await adapter.send(_Binding("emp@example.com"), RenderedMessage(text="hi"))
    assert result.ok is False
    assert "not configured" in result.error
