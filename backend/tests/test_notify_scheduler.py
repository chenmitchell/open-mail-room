"""Daily reminder/unclaimed sweep state transitions (M3-01 item 6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import (
    MailStatus,
    MailType,
    NotificationChannel,
    NotificationTemplate,
    Refrigeration,
)
from app.models.mail_item import MailItem
from app.models.notification import Notification
from app.models.notification_binding import NotificationBinding
from app.notify.scheduler import run_daily_reminder_sweep


async def _make_employee(db_session, name="員工", department_id=None) -> Employee:
    emp = Employee(name=name, aliases=[], department_id=department_id)
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


async def _make_item(db_session, *, employee, received_at, status=MailStatus.received) -> MailItem:
    item = MailItem(
        item_no=f"IN-SCHED-{employee.id[:8]}-{received_at.timestamp()}",
        direction="inbound",
        mail_type=MailType.parcel,
        recipient_employee_id=employee.id,
        recipient_name_raw=employee.name,
        received_at=received_at,
        status=status,
        refrigeration=Refrigeration.none,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest.mark.asyncio
async def test_scheduler_sends_reminder_after_remind_days(db_session):
    employee = await _make_employee(db_session)
    old = datetime.now(timezone.utc) - timedelta(days=3)
    item = await _make_item(db_session, employee=employee, received_at=old)

    stats = await run_daily_reminder_sweep(db_session)
    assert stats["reminded"] == 1
    assert stats["unclaimed"] == 0

    refreshed = await db_session.get(MailItem, item.id)
    await db_session.refresh(refreshed)
    assert refreshed.remind_count == 1
    assert refreshed.status == MailStatus.received  # reminder alone doesn't change status


@pytest.mark.asyncio
async def test_scheduler_does_not_double_remind(db_session):
    employee = await _make_employee(db_session)
    old = datetime.now(timezone.utc) - timedelta(days=3)
    await _make_item(db_session, employee=employee, received_at=old)

    stats1 = await run_daily_reminder_sweep(db_session)
    assert stats1["reminded"] == 1

    stats2 = await run_daily_reminder_sweep(db_session)
    assert stats2["reminded"] == 0  # remind_count is now > 0, gate holds


@pytest.mark.asyncio
async def test_scheduler_marks_unclaimed_after_unclaimed_days_and_notifies_manager(db_session):
    manager = await _make_employee(db_session, name="部門主管")
    dept = Department(name="業務部", code="sales", manager_employee_id=manager.id)
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)

    employee = await _make_employee(db_session, name="小職員", department_id=dept.id)

    for who in (employee, manager):
        db_session.add(
            NotificationBinding(
                employee_id=who.id, channel=NotificationChannel.email, address=f"{who.id}@x.com"
            )
        )
    await db_session.commit()

    very_old = datetime.now(timezone.utc) - timedelta(days=10)
    item = await _make_item(
        db_session, employee=employee, received_at=very_old, status=MailStatus.notified
    )

    stats = await run_daily_reminder_sweep(db_session)
    assert stats["unclaimed"] == 1

    # The sweep launches fire-and-forget delivery for the employee+manager
    # notifications it just queued -- drain them (see tests/_helpers.py)
    # before this test's own session touches the DB again.
    from tests._helpers import drain_background_notification_tasks

    await drain_background_notification_tasks()

    refreshed = await db_session.get(MailItem, item.id)
    await db_session.refresh(refreshed)
    assert refreshed.status == MailStatus.unclaimed

    result = await db_session.execute(
        select(Notification).where(Notification.mail_item_id == item.id)
    )
    notifications = result.scalars().all()
    employee_ids_notified = {n.employee_id for n in notifications}
    assert employee.id in employee_ids_notified
    assert manager.id in employee_ids_notified


@pytest.mark.asyncio
async def test_scheduler_does_not_double_notify_reminder_and_overdue_in_same_run(db_session):
    """M3-R1 suggestion (adopted): an item old enough to satisfy *both* the
    reminder and unclaimed cutoffs in a single sweep call (e.g. the sweep
    hadn't run in a while, or is running for the first time against a
    backlog) must only get the `overdue` notification, not `reminder`
    immediately followed by `overdue` in the same run."""
    employee = await _make_employee(db_session)
    db_session.add(
        NotificationBinding(
            employee_id=employee.id,
            channel=NotificationChannel.email,
            address=f"{employee.id}@x.com",
        )
    )
    await db_session.commit()

    very_old = datetime.now(timezone.utc) - timedelta(days=10)
    item = await _make_item(db_session, employee=employee, received_at=very_old)
    assert item.remind_count == 0

    stats = await run_daily_reminder_sweep(db_session)
    assert stats["reminded"] == 0
    assert stats["unclaimed"] == 1

    from tests._helpers import drain_background_notification_tasks

    await drain_background_notification_tasks()

    refreshed = await db_session.get(MailItem, item.id)
    await db_session.refresh(refreshed)
    assert refreshed.status == MailStatus.unclaimed
    assert refreshed.remind_count == 0

    result = await db_session.execute(
        select(Notification).where(Notification.mail_item_id == item.id)
    )
    notifications = result.scalars().all()
    # Exactly one notification (overdue) for the employee -- not one
    # `reminder` plus one `overdue`.
    employee_notifications = [n for n in notifications if n.employee_id == employee.id]
    assert len(employee_notifications) == 1
    assert employee_notifications[0].template == NotificationTemplate.overdue


@pytest.mark.asyncio
async def test_scheduler_ignores_already_picked_up_items(db_session):
    employee = await _make_employee(db_session)
    very_old = datetime.now(timezone.utc) - timedelta(days=10)
    item = await _make_item(
        db_session, employee=employee, received_at=very_old, status=MailStatus.picked_up
    )

    stats = await run_daily_reminder_sweep(db_session)
    assert stats["unclaimed"] == 0

    refreshed = await db_session.get(MailItem, item.id)
    await db_session.refresh(refreshed)
    assert refreshed.status == MailStatus.picked_up


@pytest.mark.asyncio
async def test_scheduler_respects_configured_thresholds(db_session):
    from app.notify.settings_store import set_setting

    await set_setting(db_session, "notify.remind_days", 1)
    await set_setting(db_session, "notify.unclaimed_days", 2)

    employee = await _make_employee(db_session)
    recent = datetime.now(timezone.utc) - timedelta(days=1, hours=1)
    item = await _make_item(db_session, employee=employee, received_at=recent)

    stats = await run_daily_reminder_sweep(db_session)
    assert stats["reminded"] == 1
    assert stats["unclaimed"] == 0

    refreshed = await db_session.get(MailItem, item.id)
    await db_session.refresh(refreshed)
    assert refreshed.status == MailStatus.received
