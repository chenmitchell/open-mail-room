"""Generic outbound-HTTP notification channel ("讓公司串自有系統/內部 IM",
05-NOTIFICATIONS.md section 2). `binding.address` is the URL the employee
bound (SSRF-checked at bind time). Signed the same way as the admin
`webhook_endpoints` subscriptions (03-API-SPEC.md section 3 HMAC scheme) so
a receiver can share verification code between the two.
"""

from __future__ import annotations

import json

import httpx

from app.notify.base import RenderedMessage, SendResult
from app.notify.http import send_http
from app.security.ssrf import UnsafeBaseUrlError, check_base_url_allowed
from app.webhooks.signing import sign_payload


class GenericWebhookAdapter:
    slug = "webhook"

    def __init__(self, *, hmac_secret: str, client: httpx.AsyncClient | None = None) -> None:
        self._secret = hmac_secret
        self._client = client

    async def send(self, binding, message: RenderedMessage) -> SendResult:
        # M3-R1 suggestion (adopted): re-run the SSRF check right before
        # actually sending, not just once at bind time (app/api/v1/bindings.py)
        # -- narrows (does not fully close, see app/security/ssrf.py's own
        # docstring on DNS-rebinding scope) the window between "URL looked
        # safe when the employee bound it" and "URL resolves somewhere
        # private by the time we actually deliver to it".
        try:
            check_base_url_allowed(binding.address, allow_private_network=False)
        except UnsafeBaseUrlError as exc:
            return SendResult(ok=False, error=f"Webhook address failed SSRF re-check: {exc}")

        body = json.dumps({"text": message.text}, separators=(",", ":"), sort_keys=True)
        headers = {
            "Content-Type": "application/json",
            "X-OpenMailroom-Signature": sign_payload(self._secret, body),
        }
        try:
            resp = await send_http(
                "POST", binding.address, content=body, headers=headers, client=self._client
            )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"Webhook request failed: {exc}")

        if 200 <= resp.status_code < 300:
            return SendResult(ok=True)
        return SendResult(
            ok=False, error=f"Webhook delivery failed: HTTP {resp.status_code} {resp.text[:300]}"
        )
