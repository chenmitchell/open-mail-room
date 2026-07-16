"""LINE Messaging API push adapter.

LINE Notify was discontinued 2025/3/31 (05-NOTIFICATIONS.md section 1) --
this always goes through the official-account Messaging API `push` endpoint,
authenticated with a long-lived channel access token (admin-configured,
encrypted at rest, see app/notify/settings_store.py).
"""

from __future__ import annotations

import httpx

from app.notify.base import RenderedMessage, SendResult
from app.notify.http import send_http

PUSH_URL = "https://api.line.me/v2/bot/message/push"
REPLY_URL = "https://api.line.me/v2/bot/message/reply"


class LineAdapter:
    slug = "line"

    def __init__(
        self, *, channel_access_token: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._token = channel_access_token
        self._client = client

    async def send(self, binding, message: RenderedMessage) -> SendResult:
        if not self._token:
            return SendResult(ok=False, error="LINE channel access token is not configured")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        payload = {
            "to": binding.address,
            "messages": [{"type": "text", "text": message.text[:5000]}],
        }
        try:
            resp = await send_http(
                "POST", PUSH_URL, headers=headers, json=payload, client=self._client
            )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"LINE push request failed: {exc}")

        if resp.status_code == 200:
            return SendResult(ok=True)
        return SendResult(
            ok=False, error=f"LINE push failed: HTTP {resp.status_code} {resp.text[:300]}"
        )


async def reply_text(
    token: str, reply_token: str, text: str, *, client: httpx.AsyncClient | None = None
) -> SendResult:
    """Best-effort reply to a webhook event (e.g. "綁定成功") -- used by
    app/api/v1/channel_webhooks.py after a successful binding-code match.
    Failure here is never fatal to the binding itself.
    """
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text[:5000]}]}
    try:
        resp = await send_http("POST", REPLY_URL, headers=headers, json=payload, client=client)
    except httpx.HTTPError as exc:
        return SendResult(ok=False, error=str(exc))
    if resp.status_code == 200:
        return SendResult(ok=True)
    return SendResult(ok=False, error=f"HTTP {resp.status_code}")
