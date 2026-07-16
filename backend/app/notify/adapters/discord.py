"""Discord Webhook adapter. `binding.address` is the webhook URL the
employee bound (SSRF-checked at bind time)."""

from __future__ import annotations

import httpx

from app.notify.base import RenderedMessage, SendResult
from app.notify.http import send_http
from app.security.ssrf import UnsafeBaseUrlError, check_base_url_allowed


class DiscordAdapter:
    slug = "discord"

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def send(self, binding, message: RenderedMessage) -> SendResult:
        # M3-R1 suggestion (adopted): re-check SSRF immediately before send,
        # see app/notify/adapters/webhook.py for the rationale.
        try:
            check_base_url_allowed(binding.address, allow_private_network=False)
        except UnsafeBaseUrlError as exc:
            return SendResult(ok=False, error=f"Discord address failed SSRF re-check: {exc}")

        try:
            resp = await send_http(
                "POST", binding.address, json={"content": message.text}, client=self._client
            )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"Discord webhook request failed: {exc}")

        # Discord's webhook execute endpoint returns 204 No Content on
        # success by default (200 if `?wait=true`); treat any 2xx as ok.
        if 200 <= resp.status_code < 300:
            return SendResult(ok=True)
        return SendResult(
            ok=False, error=f"Discord webhook failed: HTTP {resp.status_code} {resp.text[:300]}"
        )
