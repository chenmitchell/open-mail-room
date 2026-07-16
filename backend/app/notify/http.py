"""Shared outbound-HTTP helper for notify adapters and the webhook publisher.

Every adapter accepts an optional `client: httpx.AsyncClient` for tests to
inject a mocked client (via `httpx.MockTransport` or a plain stub with a
`.request`/`.post` coroutine) without monkeypatching module globals. When no
client is given, a short-lived one is created per call.
"""

from __future__ import annotations

import httpx

DEFAULT_TIMEOUT = 10.0


async def send_http(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json: object | None = None,
    content: str | bytes | None = None,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> httpx.Response:
    if client is not None:
        return await client.request(method, url, headers=headers, json=json, content=content)
    async with httpx.AsyncClient(timeout=timeout) as owned:
        return await owned.request(method, url, headers=headers, json=json, content=content)
