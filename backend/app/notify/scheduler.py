"""Daily reminder/unclaimed sweep (05-NOTIFICATIONS.md section 5 / the task
brief's item 6): scans `received`/`notified` mail items, sends a `reminder`
once they've sat for `notify.remind_days` (default 2) days, and flips them
to `unclaimed` (+ notifies the employee *and* their department manager with
the `overdue` template) once they've sat for `notify.unclaimed_days`
(default 7) days.

Not wired to a cron by this milestone (no scheduler process exists yet in
this single-process app) -- exposed as a plain async function so it can be
invoked by an external cron hitting a future admin endpoint, a systemd timer
running `python -m app.notify.scheduler`, or directly by tests. Idempotent:
`remind_count` gates the reminder (never sent twice) and the unclaimed sweep
only touches items still in `received`/`notified` (never re-flips an already
`unclaimed`/terminal item).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import MailStatus, NotificationTemplate
from app.models.mail_item import MailItem
from app.notify.settings_store import get_int_setting
from app.notify.worker import launch_delivery_for_many
from app.services.notify import queue_notifications_for_item
from app.webhooks.events import EVENT_ITEM_REMINDER, EVENT_ITEM_UNCLAIMED
from app.webhooks.publisher import launch_publish_event

_ACTIVE_STATUSES = (MailStatus.received, MailStatus.notified)


async def _queue_and_launch(
    session: AsyncSession, *, mail_item_id: str, employee_id: str, template: NotificationTemplate
) -> None:
    created = await queue_notifications_for_item(
        session, mail_item_id=mail_item_id, employee_id=employee_id, template=template
    )
    launch_delivery_for_many([n.id for n in created])


async def run_daily_reminder_sweep(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    remind_days = await get_int_setting(session, "notify.remind_days", default=2)
    unclaimed_days = await get_int_setting(session, "notify.unclaimed_days", default=7)

    remind_cutoff = now - timedelta(days=remind_days)
    unclaimed_cutoff = now - timedelta(days=unclaimed_days)

    stats = {"reminded": 0, "unclaimed": 0}

    # M3-R1 suggestion (adopted): exclude items that are *also* old enough
    # for the unclaimed/overdue sweep below in this same run. Without this,
    # an item that hadn't been swept in a while (or is being swept for the
    # first time against a backlog) could satisfy both queries in one call --
    # `remind_count == 0` is still true and `received_at` is far enough in
    # the past for *both* cutoffs -- and would get a `reminder` notification
    # immediately followed by an `overdue` one in the very same sweep. The
    # unclaimed branch already implies "overdue enough that a reminder is
    # moot"; only fire the reminder when the item is old enough for *that*
    # but not yet old enough to jump straight to unclaimed.
    reminder_stmt = select(MailItem).where(
        MailItem.status.in_(_ACTIVE_STATUSES),
        MailItem.received_at <= remind_cutoff,
        MailItem.received_at > unclaimed_cutoff,
        MailItem.remind_count == 0,
    )
    for item in (await session.execute(reminder_stmt)).scalars().all():
        item.remind_count += 1
        if item.recipient_employee_id:
            await _queue_and_launch(
                session,
                mail_item_id=item.id,
                employee_id=item.recipient_employee_id,
                template=NotificationTemplate.reminder,
            )
        stats["reminded"] += 1
        await session.flush()
        await launch_publish_event(session, event=EVENT_ITEM_REMINDER, mail_item_id=item.id)

    unclaimed_stmt = select(MailItem).where(
        MailItem.status.in_(_ACTIVE_STATUSES),
        MailItem.received_at <= unclaimed_cutoff,
    )
    for item in (await session.execute(unclaimed_stmt)).scalars().all():
        item.status = MailStatus.unclaimed
        stats["unclaimed"] += 1
        await session.flush()

        if item.recipient_employee_id:
            await _queue_and_launch(
                session,
                mail_item_id=item.id,
                employee_id=item.recipient_employee_id,
                template=NotificationTemplate.overdue,
            )
            employee = await session.get(Employee, item.recipient_employee_id)
            if employee is not None and employee.department_id:
                dept = await session.get(Department, employee.department_id)
                if (
                    dept is not None
                    and dept.manager_employee_id
                    and dept.manager_employee_id != item.recipient_employee_id
                ):
                    await _queue_and_launch(
                        session,
                        mail_item_id=item.id,
                        employee_id=dept.manager_employee_id,
                        template=NotificationTemplate.overdue,
                    )

        await launch_publish_event(session, event=EVENT_ITEM_UNCLAIMED, mail_item_id=item.id)

    await session.commit()
    return stats
