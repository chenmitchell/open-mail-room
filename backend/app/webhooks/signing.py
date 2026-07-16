"""HMAC request signing shared by:
- the outbound admin-webhook publisher (app/webhooks/publisher.py), and
- the notification-bindings generic "webhook" channel
  (app/notify/adapters/webhook.py),

both per 03-API-SPEC.md section 3:

    X-OpenMailroom-Signature: t=<unix>,v1=HMAC_SHA256(secret, t + "." + body)

with a 5-minute replay window on verification.
"""

from __future__ import annotations

import hashlib
import hmac
import time

DEFAULT_MAX_SKEW_SECONDS = 300


def sign_payload(secret: str, body: str, *, timestamp: int | None = None) -> str:
    t = timestamp if timestamp is not None else int(time.time())
    mac = hmac.new(secret.encode("utf-8"), f"{t}.{body}".encode(), hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def _parse_header(header_value: str) -> tuple[str | None, str | None]:
    parts: dict[str, str] = {}
    for chunk in header_value.split(","):
        key, _, value = chunk.strip().partition("=")
        if key and value:
            parts[key] = value
    return parts.get("t"), parts.get("v1")


def verify_signature(
    secret: str,
    body: str,
    header_value: str | None,
    *,
    max_skew_seconds: int = DEFAULT_MAX_SKEW_SECONDS,
    now: int | None = None,
) -> bool:
    """Recomputes the HMAC from `secret` + `body` + the timestamp embedded in
    the header and compares it (constant-time) against the `v1` value,
    additionally rejecting anything outside the replay window."""
    if not header_value:
        return False
    t_raw, v1 = _parse_header(header_value)
    if not t_raw or not v1:
        return False
    try:
        t_int = int(t_raw)
    except ValueError:
        return False

    current = now if now is not None else int(time.time())
    if abs(current - t_int) > max_skew_seconds:
        return False

    expected = hmac.new(
        secret.encode("utf-8"), f"{t_raw}.{body}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, v1)
