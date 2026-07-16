"""Telegram Bot API adapter. `binding.address` is the chat_id captured during
the `/start <code>` deep-link binding flow."""

from __future__ import annotations

import httpx

from app.notify.base import RenderedMessage, SendResult
from app.notify.http import send_http


class TelegramAdapter:
    slug = "telegram"

    def __init__(self, *, bot_token: str, client: httpx.AsyncClient | None = None) -> None:
        self._token = bot_token
        self._client = client

    async def send(self, binding, message: RenderedMessage) -> SendResult:
        if not self._token:
            return SendResult(ok=False, error="Telegram bot token is not configured")
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {"chat_id": binding.address, "text": message.text[:4096]}
        try:
            resp = await send_http("POST", url, json=payload, client=self._client)
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"Telegram request failed: {exc}")

        if resp.status_code == 200:
            try:
                body = resp.json()
            except ValueError:
                return SendResult(ok=False, error="Telegram returned a non-JSON body")
            if body.get("ok"):
                return SendResult(ok=True)
            return SendResult(ok=False, error=f"Telegram API error: {body.get('description')}")
        return SendResult(ok=False, error=f"Telegram push failed: HTTP {resp.status_code}")
