"""Slack Incoming Webhook adapter. `binding.address` is the webhook URL the
employee pasted in when binding this channel (validated against the SSRF
guard at bind time, see app/api/v1/bindings.py)."""

from __future__ import annotations

import httpx

from app.notify.base import RenderedMessage, SendResult
from app.notify.http import send_http
from app.security.ssrf import UnsafeBaseUrlError, check_base_url_allowed


class SlackAdapter:
    slug = "slack"

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def send(self, binding, message: RenderedMessage) -> SendResult:
        # M3-R1 suggestion (adopted): re-check SSRF immediately before send,
        # see app/notify/adapters/webhook.py for the rationale.
        try:
            check_base_url_allowed(binding.address, allow_private_network=False)
        except UnsafeBaseUrlError as exc:
            return SendResult(ok=False, error=f"Slack address failed SSRF re-check: {exc}")

        try:
            resp = await send_http(
                "POST", binding.address, json={"text": message.text}, client=self._client
            )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"Slack webhook request failed: {exc}")

        if 200 <= resp.status_code < 300:
            return SendResult(ok=True)
        return SendResult(
            ok=False, error=f"Slack webhook failed: HTTP {resp.status_code} {resp.text[:300]}"
        )
