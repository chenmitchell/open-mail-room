"""Builds the right `NotifyChannel` adapter for a `NotificationChannel`,
loading its configuration (tokens, SMTP host, HMAC secret) from the
`settings` table via app/notify/settings_store.py.
"""

from __future__ import annotations

import secrets as _secrets

import httpx

from app.models.enums import NotificationChannel
from app.notify.adapters.discord import DiscordAdapter
from app.notify.adapters.email import EmailAdapter, SmtpConfig
from app.notify.adapters.line import LineAdapter
from app.notify.adapters.slack import SlackAdapter
from app.notify.adapters.telegram import TelegramAdapter
from app.notify.adapters.webhook import GenericWebhookAdapter
from app.notify.base import NotifyChannel
from app.notify.settings_store import get_setting, set_setting

# Settings keys (see app/notify/settings_store.py for the secret-at-rest
# handling of the ones marked "(secret)").
KEY_LINE_TOKEN = "notify.line.channel_access_token"  # (secret)
KEY_LINE_SECRET = "notify.line.channel_secret"  # (secret)
KEY_TELEGRAM_TOKEN = "notify.telegram.bot_token"  # (secret)
KEY_TELEGRAM_BOT_USERNAME = "notify.telegram.bot_username"
KEY_SMTP_HOST = "notify.smtp.host"
KEY_SMTP_PORT = "notify.smtp.port"
KEY_SMTP_TLS = "notify.smtp.use_tls"
KEY_SMTP_FROM = "notify.smtp.from_addr"
KEY_SMTP_USERNAME = "notify.smtp.username"
KEY_SMTP_PASSWORD = "notify.smtp.password"  # (secret)
KEY_WEBHOOK_HMAC_SECRET = "notify.webhook.hmac_secret"  # (secret)


async def get_line_channel_secret(session) -> str | None:
    return await get_setting(session, KEY_LINE_SECRET, default=None)


async def get_telegram_webhook_secret(session) -> str | None:
    return await get_setting(session, "notify.telegram.webhook_secret", default=None)


async def _get_or_create_webhook_hmac_secret(session) -> str:
    existing = await get_setting(session, KEY_WEBHOOK_HMAC_SECRET, default=None)
    if existing:
        return str(existing)
    generated = _secrets.token_urlsafe(32)
    await set_setting(session, KEY_WEBHOOK_HMAC_SECRET, generated, secret=True)
    return generated


async def build_adapter(
    session, channel: NotificationChannel, *, client: httpx.AsyncClient | None = None
) -> NotifyChannel:
    if channel == NotificationChannel.line:
        token = await get_setting(session, KEY_LINE_TOKEN, default="")
        return LineAdapter(channel_access_token=str(token or ""), client=client)

    if channel == NotificationChannel.telegram:
        token = await get_setting(session, KEY_TELEGRAM_TOKEN, default="")
        return TelegramAdapter(bot_token=str(token or ""), client=client)

    if channel == NotificationChannel.slack:
        return SlackAdapter(client=client)

    if channel == NotificationChannel.discord:
        return DiscordAdapter(client=client)

    if channel == NotificationChannel.webhook:
        secret = await _get_or_create_webhook_hmac_secret(session)
        return GenericWebhookAdapter(hmac_secret=secret, client=client)

    if channel == NotificationChannel.email:
        cfg = SmtpConfig(
            host=str(await get_setting(session, KEY_SMTP_HOST, default="")),
            port=int(await get_setting(session, KEY_SMTP_PORT, default=587)),
            use_tls=bool(await get_setting(session, KEY_SMTP_TLS, default=True)),
            username=await get_setting(session, KEY_SMTP_USERNAME, default=None),
            password=await get_setting(session, KEY_SMTP_PASSWORD, default=None),
            from_addr=str(
                await get_setting(session, KEY_SMTP_FROM, default="noreply@openmailroom.local")
            ),
        )
        return EmailAdapter(config=cfg)

    raise ValueError(f"No adapter registered for channel '{channel}'")
