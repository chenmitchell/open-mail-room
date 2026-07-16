"""Background notification delivery (M3-01).

Shape mirrors app/ocr/pipeline.py: a fire-and-forget `asyncio.create_task`
per unit of work (here, one `Notification` row), doing its own bounded
retry-with-backoff loop *inside* that single task call (not a persistent
polling loop -- see the module docstring reasoning in worker tests / the
implementation report for why a perpetual background loop was rejected: it
would leak across the test suite's per-test `app` fixture). A startup
"orphan sweep" (called from app/main.py, like
`app.ocr.pipeline.sweep_orphan_ocr_jobs`) clears the `locked_at` marker left
behind by a task that never got to finish (process crash) and re-launches
delivery for those rows so they aren't stuck forever.

Multi-binding strategy (`notify.strategy` setting, "all" | "first_success",
default "all"): "all" sends every binding independently (each is its own
Notification row, queued at creation time by app/services/notify.py).
"first_success" still queues one row per binding up front (so nothing about
enqueueing changes), but at delivery time, before attempting a row, checks
whether a sibling row for the same (mail_item_id, employee_id, template)
has already reached `sent` -- if so this row is dead-lettered as "skipped"
without ever attempting delivery. This check happens on every delivery
attempt (not just a single up-front pass), so it stays correct even when
rows are processed across multiple, temporally-separated background tasks.

M4-01: a Notification row now targets either a mail_item (inbound templates)
or an outbound_item (the `outbound_shipped` template) -- see
app/models/notification.py's docstring for the invariant. `_attempt_delivery`
branches on which one is set; the mail-item-only "received -> notified"
status flip and its `item.notified` webhook stay mail-item-specific (an
outbound "shipped" notification doesn't have an analogous follow-up state).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.models.employee import Employee
from app.models.enums import (
    MailStatus,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
)
from app.models.mail_item import MailItem
from app.models.notification import Notification
from app.models.notification_binding import NotificationBinding
from app.models.outbound_item import OutboundItem
from app.notify.admin_alert import alert_admin
from app.notify.registry import build_adapter
from app.notify.settings_store import get_bool_setting, get_int_setting, get_setting, set_setting
from app.notify.templates import render_notification, render_outbound_shipped
from app.webhooks.events import EVENT_ITEM_NOTIFIED
from app.webhooks.publisher import launch_publish_event

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
_BACKOFF_BASE_SECONDS = 0.02
# A `locked_at` older than this at startup can only mean the process that
# set it is gone.
STALE_LOCK_SECONDS = 300

KEY_STRATEGY = "notify.strategy"
KEY_LINE_QUOTA_WARN = "notify.line.quota_warn_threshold"
KEY_LINE_QUOTA_HARD = "notify.line.quota_hard_limit"
KEY_LINE_HARD_STOP = "notify.line.hard_stop_at_quota"

_background_tasks: set[asyncio.Task] = set()


def _backoff_seconds(attempt: int) -> float:
    return _BACKOFF_BASE_SECONDS * (2**attempt)


def launch_delivery(notification_id: str) -> None:
    task = asyncio.create_task(deliver_notification_with_retry(notification_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def launch_delivery_for_many(notification_ids: list[str]) -> None:
    for notification_id in notification_ids:
        launch_delivery(notification_id)


async def sweep_orphan_notifications(session: AsyncSession) -> int:
    """Startup sweep: clear every leftover `locked_at` (the owning task is
    gone -- this process just started) and re-launch delivery for every row
    that is still `queued`, so a crash mid-delivery doesn't strand them.

    M3-R1 blocking #7: originally only looked at rows with a non-NULL
    `locked_at`, which missed a row that was queued (status=queued,
    locked_at=NULL) but never actually got its `launch_delivery(...)` call --
    e.g. the process crashed partway through the loop in
    `launch_delivery_for_many` after committing the queued rows but before
    launching every one of them. Such a row has nothing wrong with its lock
    (there never was one) so the old `locked_at IS NOT NULL` filter silently
    never picked it up again -- the notification was lost until someone
    happened to look. Matching on `status == queued` regardless of
    `locked_at` closes that gap; the `locked_at IS NOT NULL` half of the
    filter still matters for rows that *were* locked (mid-retry-backoff) when
    the process died.
    """
    stmt = select(Notification).where(
        or_(Notification.locked_at.is_not(None), Notification.status == NotificationStatus.queued)
    )
    rows = (await session.execute(stmt)).scalars().all()
    to_relaunch: list[str] = []
    for row in rows:
        row.locked_at = None
        if row.status == NotificationStatus.queued:
            to_relaunch.append(row.id)
    if rows:
        await session.commit()
    for notification_id in to_relaunch:
        launch_delivery(notification_id)
    return len(rows)


async def _resolve_binding(
    session: AsyncSession, notification: Notification
) -> NotificationBinding | None:
    if notification.binding_id:
        binding = await session.get(NotificationBinding, notification.binding_id)
        if binding is not None:
            return binding
    # Fallback for rows queued before `binding_id` existed, or where the
    # bound binding has since been deleted: pick the first still-existing
    # binding for this employee+channel.
    stmt = select(NotificationBinding).where(
        NotificationBinding.employee_id == notification.employee_id,
        NotificationBinding.channel == notification.channel,
    )
    return (await session.execute(stmt)).scalars().first()


async def _already_satisfied_by_sibling(session: AsyncSession, notification: Notification) -> bool:
    strategy = await get_setting(session, KEY_STRATEGY, default="all")
    if strategy != "first_success":
        return False
    stmt = select(func.count()).select_from(Notification).where(
        Notification.mail_item_id == notification.mail_item_id,
        Notification.outbound_item_id == notification.outbound_item_id,
        Notification.employee_id == notification.employee_id,
        Notification.template == notification.template,
        Notification.status == NotificationStatus.sent,
        Notification.id != notification.id,
    )
    return (await session.execute(stmt)).scalar_one() > 0


async def _line_sent_count_this_month(session: AsyncSession, *, now: datetime) -> int:
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.count()).select_from(Notification).where(
        Notification.channel == NotificationChannel.line,
        Notification.status == NotificationStatus.sent,
        Notification.sent_at >= month_start,
    )
    return (await session.execute(stmt)).scalar_one()


async def _maybe_alert_line_quota(session: AsyncSession, *, count: int, now: datetime) -> None:
    warn_threshold = await get_int_setting(session, KEY_LINE_QUOTA_WARN, default=180)
    if count < warn_threshold:
        return
    month_key = f"notify.line.quota_alerted.{now.year:04d}-{now.month:02d}"
    already_alerted = await get_bool_setting(session, month_key, default=False)
    if already_alerted:
        return
    await set_setting(session, month_key, True)
    await alert_admin(
        session,
        kind="line_quota",
        message=(
            f"LINE monthly push count is {count}, at/above the warn threshold "
            f"({warn_threshold}). Consider the email fallback or a paid LINE plan."
        ),
        meta={"count": count, "warn_threshold": warn_threshold},
    )


async def _line_fallback_binding(
    session: AsyncSession, employee_id: str
) -> NotificationBinding | None:
    stmt = select(NotificationBinding).where(
        NotificationBinding.employee_id == employee_id,
        NotificationBinding.channel == NotificationChannel.email,
    )
    return (await session.execute(stmt)).scalars().first()


async def _render_message(
    session: AsyncSession,
    notification: Notification,
    *,
    mail_item: MailItem | None,
    outbound_item: OutboundItem | None,
):
    """M4-01: dispatch to the right template renderer depending on which of
    mail_item/outbound_item this row targets (see the module docstring)."""
    if outbound_item is not None:
        return await render_outbound_shipped(
            session, tracking_no=outbound_item.tracking_no, item_no=outbound_item.item_no
        )

    days = None
    if notification.template == NotificationTemplate.reminder:
        days = await get_int_setting(session, "notify.remind_days", default=2)
    elif notification.template == NotificationTemplate.overdue:
        days = await get_int_setting(session, "notify.unclaimed_days", default=7)

    employee = await session.get(Employee, notification.employee_id)
    return await render_notification(
        session, template=notification.template, mail_item=mail_item, employee=employee, days=days
    )


async def _attempt_delivery(
    session: AsyncSession, notification: Notification, *, now: datetime
) -> str:
    """Returns one of: "sent", "retry", "dead", "skipped"."""
    mail_item: MailItem | None = None
    outbound_item: OutboundItem | None = None

    if notification.mail_item_id:
        mail_item = await session.get(MailItem, notification.mail_item_id)
        if mail_item is None:
            notification.status = NotificationStatus.dead
            notification.error = "mail_item no longer exists"
            return "dead"
    elif notification.outbound_item_id:
        outbound_item = await session.get(OutboundItem, notification.outbound_item_id)
        if outbound_item is None:
            notification.status = NotificationStatus.dead
            notification.error = "outbound_item no longer exists"
            return "dead"
    else:
        # Should never happen (app.services.notify always sets exactly one),
        # but dead-letter rather than crash if it somehow does.
        notification.status = NotificationStatus.dead
        notification.error = "neither mail_item_id nor outbound_item_id is set"
        return "dead"

    employee = await session.get(Employee, notification.employee_id)
    if employee is None:
        notification.status = NotificationStatus.dead
        notification.error = "employee no longer exists"
        return "dead"

    if await _already_satisfied_by_sibling(session, notification):
        notification.status = NotificationStatus.dead
        notification.error = "skipped: first_success strategy, another binding already succeeded"
        return "skipped"

    binding = await _resolve_binding(session, notification)
    if binding is None:
        notification.status = NotificationStatus.dead
        notification.error = "no matching notification_binding for this employee/channel"
        return "dead"

    channel = notification.channel
    effective_binding = binding

    if channel == NotificationChannel.line:
        count = await _line_sent_count_this_month(session, now=now)
        await _maybe_alert_line_quota(session, count=count, now=now)
        hard_limit = await get_int_setting(session, KEY_LINE_QUOTA_HARD, default=200)
        hard_stop = await get_bool_setting(session, KEY_LINE_HARD_STOP, default=False)
        if hard_stop and count >= hard_limit:
            fallback = await _line_fallback_binding(session, notification.employee_id)
            if fallback is not None:
                channel = NotificationChannel.email
                effective_binding = fallback
            else:
                notification.status = NotificationStatus.dead
                notification.error = "LINE_QUOTA_EXCEEDED: monthly quota reached, no email fallback"
                return "dead"

    message = await _render_message(
        session, notification, mail_item=mail_item, outbound_item=outbound_item
    )

    adapter = await build_adapter(session, channel)
    result = await adapter.send(effective_binding, message)

    if result.ok:
        notification.status = NotificationStatus.sent
        notification.sent_at = now
        notification.error = None
        if (
            mail_item is not None
            and notification.template == NotificationTemplate.received
            and mail_item.status == MailStatus.received
        ):
            mail_item.status = MailStatus.notified
            mail_item.notified_at = now
            await session.flush()
            await launch_publish_event(
                session, event=EVENT_ITEM_NOTIFIED, mail_item_id=mail_item.id
            )
        return "sent"

    notification.error = result.error
    return "retry"


async def deliver_notification_with_retry(notification_id: str) -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            notification = await session.get(Notification, notification_id)
            if notification is None or notification.status != NotificationStatus.queued:
                return

            # M3-R1 suggestion (adopted): compare-and-swap the lock instead of
            # an unconditional write. Two callers can legitimately race to
            # deliver the same notification id -- e.g. the startup orphan
            # sweep above and a fresh `launch_delivery` call for the same row
            # both firing close together -- and without a CAS here, the
            # second caller's plain `notification.locked_at = now` would
            # silently steal the lock out from under the first caller's
            # already-running delivery attempt instead of backing off.
            now = datetime.now(timezone.utc)
            lock_result = await session.execute(
                update(Notification)
                .where(Notification.id == notification_id, Notification.locked_at.is_(None))
                .values(locked_at=now)
            )
            await session.commit()
            if lock_result.rowcount == 0:
                # Someone else already holds the lock -- back off, don't
                # double-attempt delivery.
                return
            await session.refresh(notification)

            attempt = notification.retries
            while True:
                now = datetime.now(timezone.utc)
                outcome = await _attempt_delivery(session, notification, now=now)
                if outcome in ("sent", "dead", "skipped"):
                    break
                attempt += 1
                notification.retries = attempt
                if attempt >= MAX_ATTEMPTS:
                    notification.status = NotificationStatus.dead
                    break
                notification.next_attempt_at = now + timedelta(seconds=_backoff_seconds(attempt))
                await session.flush()
                await asyncio.sleep(_backoff_seconds(attempt))

            notification.locked_at = None
            await session.commit()
        except Exception:  # noqa: BLE001 - never crash the event loop
            logger.exception("notification %s: unhandled delivery error", notification_id)
            try:
                await session.rollback()
                notification = await session.get(Notification, notification_id)
                if notification is not None:
                    notification.locked_at = None
                    await session.commit()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "notification %s: failed to clear lock after error", notification_id
                )
