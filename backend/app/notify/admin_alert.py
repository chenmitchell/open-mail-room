"""Admin alerting for notification/webhook subsystem events that need human
attention (LINE quota nearing its free-tier limit, a webhook endpoint
auto-disabled after repeated failures, ...).

There is no dedicated "admin inbox" model in this schema, so an alert is
always recorded as an append-only `audit_logs` row (action prefixed
`admin_alert.`) -- the admin UI can list/filter on that -- and, best-effort,
also emailed to `notify.admin_alert_email` (a plain, non-secret setting) if
one is configured and SMTP is set up. Email failure never raises: the audit
log row is the durable record; email is a courtesy.
"""

from __future__ import annotations

from typing import Any

from app.models.enums import ActorType, NotificationChannel
from app.notify.base import RenderedMessage
from app.notify.registry import build_adapter
from app.notify.settings_store import get_setting
from app.services.audit import record_audit


class _EmailTarget:
    """Tiny stand-in for a NotificationBinding -- EmailAdapter.send only
    reads `.address`."""

    def __init__(self, address: str) -> None:
        self.address = address


async def alert_admin(
    session, *, kind: str, message: str, meta: dict[str, Any] | None = None
) -> None:
    await record_audit(
        session,
        request=None,
        actor=None,
        actor_type=ActorType.system,
        action=f"admin_alert.{kind}",
        target_type="admin_alert",
        target_id=None,
        diff={"message": message, **(meta or {})},
    )
    await session.flush()

    admin_email = await get_setting(session, "notify.admin_alert_email", default=None)
    if not admin_email:
        return
    try:
        adapter = await build_adapter(session, NotificationChannel.email)
        await adapter.send(
            _EmailTarget(str(admin_email)),
            RenderedMessage(text=message, title=f"[Open Mail Room] {kind}"),
        )
    except Exception:  # noqa: BLE001 - alert email is best-effort only
        pass
