"""Delivery worker: retry/backoff/dead-letter, multi-binding strategy, and
LINE monthly quota alerting (M3-01 item 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.notify.worker as worker_module
from app.models.employee import Employee
from app.models.enums import (
    MailStatus,
    MailType,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
    Refrigeration,
)
from app.models.mail_item import MailItem
from app.models.notification import Notification
from app.models.notification_binding import NotificationBinding
from app.notify.base import SendResult
from app.notify.settings_store import set_setting


async def _make_item(db_session, *, employee: Employee) -> MailItem:
    item = MailItem(
        item_no=f"IN-TEST-{employee.id[:8]}",
        direction="inbound",
        mail_type=MailType.parcel,
        recipient_employee_id=employee.id,
        recipient_name_raw=employee.name,
        received_at=datetime.now(timezone.utc),
        status=MailStatus.received,
        refrigeration=Refrigeration.none,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _make_employee(db_session, name="員工A") -> Employee:
    emp = Employee(name=name, aliases=[], pickup_code=None)
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


async def _make_binding(db_session, employee, channel, address) -> NotificationBinding:
    binding = NotificationBinding(employee_id=employee.id, channel=channel, address=address)
    db_session.add(binding)
    await db_session.commit()
    await db_session.refresh(binding)
    return binding


async def _make_notification(
    db_session, *, item, employee, binding, template=NotificationTemplate.received
) -> Notification:
    n = Notification(
        mail_item_id=item.id,
        employee_id=employee.id,
        channel=binding.channel,
        template=template,
        status=NotificationStatus.queued,
        binding_id=binding.id,
    )
    db_session.add(n)
    await db_session.commit()
    await db_session.refresh(n)
    return n


class _ScriptedAdapter:
    """Fails `fail_times` calls, then succeeds forever after."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    async def send(self, binding, message):
        self.calls += 1
        if self.calls <= self.fail_times:
            return SendResult(ok=False, error=f"boom #{self.calls}")
        return SendResult(ok=True)


class _AlwaysFailAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def send(self, binding, message):
        self.calls += 1
        return SendResult(ok=False, error="permanent failure")


@pytest.mark.asyncio
async def test_worker_retries_then_succeeds(db_session, monkeypatch):
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    binding = await _make_binding(
        db_session, employee, NotificationChannel.slack, "https://hooks.slack.com/x"
    )
    notification = await _make_notification(
        db_session, item=item, employee=employee, binding=binding
    )

    adapter = _ScriptedAdapter(fail_times=2)

    async def _fake_build_adapter(session, channel, client=None):
        return adapter

    monkeypatch.setattr(worker_module, "build_adapter", _fake_build_adapter)

    await worker_module.deliver_notification_with_retry(notification.id)

    refreshed = await db_session.get(Notification, notification.id)
    await db_session.refresh(refreshed)
    assert refreshed.status == NotificationStatus.sent
    assert refreshed.retries == 2
    assert adapter.calls == 3


@pytest.mark.asyncio
async def test_worker_dead_letters_after_max_attempts(db_session, monkeypatch):
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    binding = await _make_binding(
        db_session, employee, NotificationChannel.slack, "https://hooks.slack.com/y"
    )
    notification = await _make_notification(
        db_session, item=item, employee=employee, binding=binding
    )

    adapter = _AlwaysFailAdapter()

    async def _fake_build_adapter(session, channel, client=None):
        return adapter

    monkeypatch.setattr(worker_module, "build_adapter", _fake_build_adapter)

    await worker_module.deliver_notification_with_retry(notification.id)

    refreshed = await db_session.get(Notification, notification.id)
    await db_session.refresh(refreshed)
    assert refreshed.status == NotificationStatus.dead
    assert refreshed.retries == worker_module.MAX_ATTEMPTS
    assert adapter.calls == worker_module.MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_worker_first_success_strategy_skips_sibling(db_session, monkeypatch):
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    await set_setting(db_session, "notify.strategy", "first_success")

    winning_binding = await _make_binding(
        db_session, employee, NotificationChannel.slack, "https://hooks.slack.com/win"
    )
    loser_binding = await _make_binding(
        db_session, employee, NotificationChannel.discord, "https://discord.com/api/webhooks/lose"
    )

    winner = await _make_notification(
        db_session, item=item, employee=employee, binding=winning_binding
    )
    loser = await _make_notification(
        db_session, item=item, employee=employee, binding=loser_binding
    )

    ok_adapter = _ScriptedAdapter(fail_times=0)

    async def _fake_build_adapter(session, channel, client=None):
        return ok_adapter

    monkeypatch.setattr(worker_module, "build_adapter", _fake_build_adapter)

    await worker_module.deliver_notification_with_retry(winner.id)
    winner_row = await db_session.get(Notification, winner.id)
    await db_session.refresh(winner_row)
    assert winner_row.status == NotificationStatus.sent

    await worker_module.deliver_notification_with_retry(loser.id)
    loser_row = await db_session.get(Notification, loser.id)
    await db_session.refresh(loser_row)
    assert loser_row.status == NotificationStatus.dead
    assert "skipped" in loser_row.error
    # The loser's adapter must never actually have been called.
    assert ok_adapter.calls == 1


@pytest.mark.asyncio
async def test_worker_all_strategy_sends_every_binding(db_session, monkeypatch):
    """Default strategy ("all"): both bindings get a real delivery attempt,
    neither is skipped as a "sibling already succeeded"."""
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)

    b1 = await _make_binding(db_session, employee, NotificationChannel.slack, "https://hooks.slack.com/a")
    b2 = await _make_binding(db_session, employee, NotificationChannel.discord, "https://discord.com/api/webhooks/b")
    n1 = await _make_notification(db_session, item=item, employee=employee, binding=b1)
    n2 = await _make_notification(db_session, item=item, employee=employee, binding=b2)

    ok_adapter = _ScriptedAdapter(fail_times=0)

    async def _fake_build_adapter(session, channel, client=None):
        return ok_adapter

    monkeypatch.setattr(worker_module, "build_adapter", _fake_build_adapter)

    await worker_module.deliver_notification_with_retry(n1.id)
    await worker_module.deliver_notification_with_retry(n2.id)

    row1 = await db_session.get(Notification, n1.id)
    row2 = await db_session.get(Notification, n2.id)
    await db_session.refresh(row1)
    await db_session.refresh(row2)
    assert row1.status == NotificationStatus.sent
    assert row2.status == NotificationStatus.sent
    assert ok_adapter.calls == 2


@pytest.mark.asyncio
async def test_worker_line_quota_warning_alerts_admin_once(db_session, monkeypatch):
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    binding = await _make_binding(db_session, employee, NotificationChannel.line, "Uquota")

    # Seed 180 already-sent LINE notifications this month to cross the
    # (default) warn threshold.
    month_start = datetime.now(timezone.utc).replace(day=1)
    for i in range(180):
        n = Notification(
            mail_item_id=item.id,
            employee_id=employee.id,
            channel=NotificationChannel.line,
            template=NotificationTemplate.received,
            status=NotificationStatus.sent,
            sent_at=month_start + timedelta(hours=i),
        )
        db_session.add(n)
    await db_session.commit()

    notification = await _make_notification(
        db_session, item=item, employee=employee, binding=binding
    )

    ok_adapter = _ScriptedAdapter(fail_times=0)

    async def _fake_build_adapter(session, channel, client=None):
        return ok_adapter

    monkeypatch.setattr(worker_module, "build_adapter", _fake_build_adapter)

    await worker_module.deliver_notification_with_retry(notification.id)

    from app.models.audit_log import AuditLog

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "admin_alert.line_quota")
    )
    logs = result.scalars().all()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_worker_line_hard_stop_falls_back_to_email_binding(db_session, monkeypatch):
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    line_binding = await _make_binding(db_session, employee, NotificationChannel.line, "Uhard")
    await _make_binding(db_session, employee, NotificationChannel.email, "fallback@example.com")

    await set_setting(db_session, "notify.line.hard_stop_at_quota", True)
    await set_setting(db_session, "notify.line.quota_hard_limit", 5)

    month_start = datetime.now(timezone.utc).replace(day=1)
    for i in range(5):
        n = Notification(
            mail_item_id=item.id,
            employee_id=employee.id,
            channel=NotificationChannel.line,
            template=NotificationTemplate.received,
            status=NotificationStatus.sent,
            sent_at=month_start + timedelta(hours=i),
        )
        db_session.add(n)
    await db_session.commit()

    notification = await _make_notification(
        db_session, item=item, employee=employee, binding=line_binding
    )

    seen_channels = []
    ok_adapter = _ScriptedAdapter(fail_times=0)

    async def _fake_build_adapter(session, channel, client=None):
        seen_channels.append(channel)
        return ok_adapter

    monkeypatch.setattr(worker_module, "build_adapter", _fake_build_adapter)

    await worker_module.deliver_notification_with_retry(notification.id)

    assert seen_channels == [NotificationChannel.email]
    refreshed = await db_session.get(Notification, notification.id)
    await db_session.refresh(refreshed)
    assert refreshed.status == NotificationStatus.sent


@pytest.mark.asyncio
async def test_sweep_relaunches_queued_rows_with_no_lock(db_session, monkeypatch):
    """M3-R1 blocking #7: a notification can be `queued` with `locked_at`
    still NULL -- e.g. the process crashed inside `launch_delivery_for_many`
    after committing the queued rows but before every one of them got its
    `launch_delivery(...)` call. The old sweep only looked at
    `locked_at IS NOT NULL`, so this row was silently never picked back up on
    restart. The fix: the sweep must also catch every `status == queued` row
    regardless of `locked_at`."""
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    binding = await _make_binding(
        db_session, employee, NotificationChannel.slack, "https://hooks.slack.com/orphan"
    )
    notification = await _make_notification(
        db_session, item=item, employee=employee, binding=binding
    )
    # Simulate "queued, never locked, never launched" -- locked_at stays
    # NULL (the model's default), nothing else touches it here.
    assert notification.locked_at is None
    assert notification.status == NotificationStatus.queued

    launched_ids: list[str] = []
    monkeypatch.setattr(worker_module, "launch_delivery", launched_ids.append)

    swept = await worker_module.sweep_orphan_notifications(db_session)

    assert swept == 1
    assert launched_ids == [notification.id]


@pytest.mark.asyncio
async def test_sweep_also_clears_and_relaunches_locked_queued_rows(db_session, monkeypatch):
    """The other half of the same sweep: a row that *was* locked (mid-retry
    when the process died) must still have its stale lock cleared and get
    relaunched -- this is the pre-existing behaviour the blocking #7 fix must
    not regress."""
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    binding = await _make_binding(
        db_session, employee, NotificationChannel.slack, "https://hooks.slack.com/locked"
    )
    notification = await _make_notification(
        db_session, item=item, employee=employee, binding=binding
    )
    notification.locked_at = datetime.now(timezone.utc)
    db_session.add(notification)
    await db_session.commit()

    launched_ids: list[str] = []
    monkeypatch.setattr(worker_module, "launch_delivery", launched_ids.append)

    swept = await worker_module.sweep_orphan_notifications(db_session)

    assert swept == 1
    assert launched_ids == [notification.id]
    refreshed = await db_session.get(Notification, notification.id)
    await db_session.refresh(refreshed)
    assert refreshed.locked_at is None


@pytest.mark.asyncio
async def test_sweep_ignores_already_terminal_rows(db_session, monkeypatch):
    """A `sent`/`dead` row with no lock is simply done -- the sweep must not
    touch or relaunch it."""
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    binding = await _make_binding(
        db_session, employee, NotificationChannel.slack, "https://hooks.slack.com/done"
    )
    notification = await _make_notification(
        db_session, item=item, employee=employee, binding=binding
    )
    notification.status = NotificationStatus.sent
    db_session.add(notification)
    await db_session.commit()

    launched_ids: list[str] = []
    monkeypatch.setattr(worker_module, "launch_delivery", launched_ids.append)

    swept = await worker_module.sweep_orphan_notifications(db_session)

    assert swept == 0
    assert launched_ids == []


@pytest.mark.asyncio
async def test_worker_lock_is_cas_second_caller_backs_off(db_session, monkeypatch):
    """M3-R1 suggestion (adopted): two concurrent callers for the same
    notification id (e.g. the orphan sweep and a fresh `launch_delivery` call
    racing) must not both proceed to deliver -- the second one to attempt the
    `locked_at IS NULL` compare-and-swap should see it already taken and back
    off instead of stealing the lock."""
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    binding = await _make_binding(
        db_session, employee, NotificationChannel.slack, "https://hooks.slack.com/race"
    )
    notification = await _make_notification(
        db_session, item=item, employee=employee, binding=binding
    )

    # Simulate "another task already holds the lock".
    notification.locked_at = datetime.now(timezone.utc)
    db_session.add(notification)
    await db_session.commit()

    adapter = _ScriptedAdapter(fail_times=0)

    async def _fake_build_adapter(session, channel, client=None):
        return adapter

    monkeypatch.setattr(worker_module, "build_adapter", _fake_build_adapter)

    await worker_module.deliver_notification_with_retry(notification.id)

    # The adapter must never have been called -- the CAS should have bailed
    # out before ever reaching delivery.
    assert adapter.calls == 0
    refreshed = await db_session.get(Notification, notification.id)
    await db_session.refresh(refreshed)
    assert refreshed.status == NotificationStatus.queued
    assert refreshed.locked_at is not None


@pytest.mark.asyncio
async def test_worker_missing_binding_dead_letters_immediately(db_session):
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    # No binding created at all -- Notification references a channel with
    # nothing to deliver to.
    notification = Notification(
        mail_item_id=item.id,
        employee_id=employee.id,
        channel=NotificationChannel.email,
        template=NotificationTemplate.received,
        status=NotificationStatus.queued,
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)

    await worker_module.deliver_notification_with_retry(notification.id)

    refreshed = await db_session.get(Notification, notification.id)
    await db_session.refresh(refreshed)
    assert refreshed.status == NotificationStatus.dead
    assert refreshed.retries == 0
