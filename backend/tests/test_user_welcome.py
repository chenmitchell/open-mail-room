import pytest

from app.services import user_welcome
from app.services.user_welcome import build_welcome_message, send_welcome_email


def test_build_welcome_message_has_credentials_and_login():
    msg = build_welcome_message(
        display_name="王小明",
        email="ming@example.com",
        initial_password="TempPass1234",
        login_url="https://mail.example.com/login",
    )
    assert "ming@example.com" in msg.text
    assert "TempPass1234" in msg.text
    assert "https://mail.example.com/login" in msg.text
    assert "修改密碼" in msg.text
    assert msg.title


@pytest.mark.asyncio
async def test_send_welcome_email_skips_when_smtp_unconfigured(monkeypatch):
    # Default settings have SMTP_HOST="" -> must skip gracefully, return False,
    # and never raise (account creation must not depend on email).
    from types import SimpleNamespace

    monkeypatch.setattr(
        user_welcome, "get_settings", lambda: SimpleNamespace(smtp_host="")
    )
    sent = await send_welcome_email(
        email="a@b.com", display_name="A", initial_password="x" * 12, login_url="u"
    )
    assert sent is False


@pytest.mark.asyncio
async def test_send_welcome_email_uses_adapter_when_configured(monkeypatch):
    from types import SimpleNamespace

    from app.notify.base import SendResult

    monkeypatch.setattr(
        user_welcome,
        "get_settings",
        lambda: SimpleNamespace(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_use_tls=True,
            smtp_username="u",
            smtp_password="p",
            smtp_from="noreply@example.com",
        ),
    )

    captured = {}

    async def fake_send(self, binding, message):
        captured["to"] = binding.address
        captured["text"] = message.text
        return SendResult(ok=True)

    monkeypatch.setattr(user_welcome.EmailAdapter, "send", fake_send)
    sent = await send_welcome_email(
        email="new@example.com",
        display_name="New",
        initial_password="InitPass1234",
        login_url="https://x/login",
    )
    assert sent is True
    assert captured["to"] == "new@example.com"
    assert "InitPass1234" in captured["text"]
