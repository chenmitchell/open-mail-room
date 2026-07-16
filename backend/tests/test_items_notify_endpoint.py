"""POST /items/{id}/notify -- manual resend (03-API-SPEC.md section 2)."""

from __future__ import annotations

from app.models.employee import Employee
from app.models.enums import NotificationChannel, UserRole
from app.models.notification_binding import NotificationBinding
from tests._helpers import drain_background_notification_tasks, login_as


async def test_manual_notify_requires_counter_or_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)
    resp = await client.post("/api/v1/items/does-not-exist/notify", json={})
    assert resp.status_code == 403


async def test_manual_notify_404_for_unknown_item(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post("/api/v1/items/does-not-exist/notify", json={})
    assert resp.status_code == 404


async def test_manual_notify_requires_recipient(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    created = (
        await client.post("/api/v1/items", json={"recipient_name_raw": "無名氏"})
    ).json()["data"]

    resp = await client.post(f"/api/v1/items/{created['id']}/notify", json={})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "ITEM_NO_RECIPIENT"


async def test_manual_notify_requires_binding(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    emp = Employee(name="王小明", aliases=[])
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)

    created = (
        await client.post(
            "/api/v1/items",
            json={"recipient_name_raw": emp.name, "recipient_employee_id": emp.id},
        )
    ).json()["data"]

    resp = await client.post(f"/api/v1/items/{created['id']}/notify", json={})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NO_NOTIFICATION_BINDING"


async def test_manual_notify_queues_and_launches_delivery(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    emp = Employee(name="王小明", aliases=[])
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)

    binding = NotificationBinding(
        employee_id=emp.id, channel=NotificationChannel.email, address="emp@example.com"
    )
    db_session.add(binding)
    await db_session.commit()

    created = (
        await client.post(
            "/api/v1/items",
            json={"recipient_name_raw": emp.name, "recipient_employee_id": emp.id},
        )
    ).json()["data"]
    # Drain the automatic on-create delivery attempt first (no SMTP
    # configured, so it will dead-letter quickly).
    await drain_background_notification_tasks()

    resp = await client.post(
        f"/api/v1/items/{created['id']}/notify", json={"template": "reminder"}
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]["queued"]) == 1

    await drain_background_notification_tasks()

    from sqlalchemy import select

    from app.models.enums import NotificationTemplate
    from app.models.notification import Notification

    result = await db_session.execute(
        select(Notification).where(
            Notification.mail_item_id == created["id"],
            Notification.template == NotificationTemplate.reminder,
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 1
