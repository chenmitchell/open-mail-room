"""GET /notifications -- M3-R1 blocking #3: the "通知失敗" (通知失敗清單)
counter-facing page (src/pages/notifications/NotificationFailuresPage.vue,
src/api/notifications.ts `listNotifications`) called this endpoint but it
didn't exist on the backend at all, so every load 404'd. Covers pagination,
the `status` filter, item_no/recipient_name denormalization, role gating, and
the M3-R1 suggestion that "first_success" skip no-ops must not show up in the
`dead` list.
"""

from __future__ import annotations

from app.models.employee import Employee
from app.models.enums import (
    MailStatus,
    MailType,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
    Refrigeration,
    UserRole,
)
from app.models.mail_item import MailItem
from app.models.notification import Notification
from tests._helpers import login_as


async def _make_item(db_session, *, employee, item_no="IN-NOTIF-001") -> MailItem:
    from datetime import datetime, timezone

    item = MailItem(
        item_no=item_no,
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


async def _make_employee(db_session, name="王小明") -> Employee:
    emp = Employee(name=name, aliases=[])
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


async def _make_notification(
    db_session,
    *,
    item,
    employee,
    status=NotificationStatus.dead,
    channel=NotificationChannel.email,
    error=None,
    retries=5,
) -> Notification:
    n = Notification(
        mail_item_id=item.id,
        employee_id=employee.id,
        channel=channel,
        template=NotificationTemplate.received,
        status=status,
        error=error,
        retries=retries,
    )
    db_session.add(n)
    await db_session.commit()
    await db_session.refresh(n)
    return n


async def test_list_notifications_requires_counter_or_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)
    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 403


async def test_list_notifications_filters_by_status_and_denormalizes(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee, item_no="IN-NOTIF-DEAD")
    dead = await _make_notification(
        db_session, item=item, employee=employee, status=NotificationStatus.dead, error="boom"
    )
    await _make_notification(
        db_session, item=item, employee=employee, status=NotificationStatus.sent
    )

    resp = await client.get("/api/v1/notifications?status=dead")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["meta"]["total"] == 1
    row = body["data"][0]
    assert row["id"] == dead.id
    assert row["item_no"] == "IN-NOTIF-DEAD"
    assert row["recipient_name"] == "王小明"
    assert row["status"] == "dead"
    assert row["error"] == "boom"


async def test_list_notifications_paginates(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    for _ in range(3):
        await _make_notification(db_session, item=item, employee=employee)

    resp = await client.get("/api/v1/notifications?status=dead&page=1&size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"] == {"total": 3, "page": 1, "size": 2}
    assert len(body["data"]) == 2

    resp2 = await client.get("/api/v1/notifications?status=dead&page=2&size=2")
    assert len(resp2.json()["data"]) == 1


async def test_list_notifications_excludes_first_success_skipped_rows(client, db_session):
    """M3-R1 suggestion (adopted): a row dead-lettered as "skipped: ..." by
    the first_success strategy (app/notify/worker.py
    `_already_satisfied_by_sibling`) is an expected no-op, not a delivery
    failure -- it must never show up in the counter-facing dead/failure
    list, even when explicitly filtering `status=dead`."""
    await login_as(client, db_session, role=UserRole.counter)
    employee = await _make_employee(db_session)
    item = await _make_item(db_session, employee=employee)
    real_failure = await _make_notification(
        db_session,
        item=item,
        employee=employee,
        status=NotificationStatus.dead,
        error="smtp timeout",
    )
    await _make_notification(
        db_session,
        item=item,
        employee=employee,
        status=NotificationStatus.dead,
        error="skipped: first_success strategy, another binding already succeeded",
    )

    resp = await client.get("/api/v1/notifications?status=dead")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 1
    assert [row["id"] for row in body["data"]] == [real_failure.id]

    # Also excluded from the unfiltered listing.
    resp_all = await client.get("/api/v1/notifications")
    ids = [row["id"] for row in resp_all.json()["data"]]
    assert real_failure.id in ids
    assert all("skipped" not in (row.get("error") or "") for row in resp_all.json()["data"])
