"""交寄 (outbound_items) endpoints -- full flow + permissions,
outbound.shipped webhook/notification triggering (03-API-SPEC.md section 2
"交寄" / section 3 events)."""

from __future__ import annotations

import re

import httpx

from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import (
    AttachmentKind,
    AttachmentOwnerType,
    NotificationChannel,
    NotificationTemplate,
    UserRole,
)
from app.models.notification import Notification
from app.models.notification_binding import NotificationBinding
from app.models.webhook_endpoint import WebhookEndpoint
from app.security.file_crypto import save_encrypted_file
from tests._helpers import create_user, drain_background_notification_tasks, login, login_as

ITEM_NO_RE = re.compile(r"^OUT-\d{8}-\d{4}$")


async def _make_department(db_session, code="eng") -> Department:
    dept = Department(name="Engineering", code=code)
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


async def _make_employee(
    db_session, *, name="王小明", department_id=None, user_id=None
) -> Employee:
    emp = Employee(name=name, aliases=[], department_id=department_id, user_id=user_id)
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


async def _make_pending_attachment(db_session):
    stored = save_encrypted_file(
        b"fake-label-bytes", subdir="outbound_photos/pending", extension="jpg"
    )
    from app.models.attachment import Attachment

    attachment = Attachment(
        owner_type=AttachmentOwnerType.outbound_item,
        owner_id="placeholder",
        kind=AttachmentKind.label_photo,
        file_path=stored["file_path"],
        sha256=stored["sha256"],
        mime="image/jpeg",
        size_bytes=stored["size_bytes"],
    )
    db_session.add(attachment)
    await db_session.commit()
    await db_session.refresh(attachment)
    attachment.owner_id = attachment.id
    await db_session.commit()
    await db_session.refresh(attachment)
    return attachment


async def test_create_outbound_requires_valid_role(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)
    resp = await client.post("/api/v1/outbound", json={"to_name": "X"})
    assert resp.status_code == 403


async def test_create_outbound_by_admin_and_item_no_format(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post("/api/v1/outbound", json={"to_name": "王小明"})
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert ITEM_NO_RE.match(body["item_no"])
    assert body["status"] == "pending"


async def test_create_outbound_sequential_same_day(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    numbers = []
    for _ in range(3):
        resp = await client.post("/api/v1/outbound", json={"to_name": "X"})
        assert resp.status_code == 201
        numbers.append(resp.json()["data"]["item_no"])
    prefix = numbers[0].rsplit("-", 1)[0]
    suffixes = [int(n.rsplit("-", 1)[1]) for n in numbers]
    assert all(n.startswith(prefix) for n in numbers)
    assert suffixes == sorted(suffixes)
    assert len(set(suffixes)) == 3


async def test_employee_create_forces_self_as_applicant(client, db_session):
    dept = await _make_department(db_session)

    user = await create_user(db_session, email="emp2@example.com", role=UserRole.employee)
    emp = await _make_employee(db_session, name="員工甲", department_id=dept.id, user_id=user.id)
    await login(client, email="emp2@example.com")

    resp = await client.post(
        "/api/v1/outbound",
        json={"to_name": "X", "applicant_employee_id": "someone-else-id"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["applicant_employee_id"] == emp.id
    assert body["department_id"] == dept.id


async def test_employee_without_linked_record_rejected(client, db_session):
    await create_user(db_session, email="emp3@example.com", role=UserRole.employee)
    await login(client, email="emp3@example.com")

    resp = await client.post("/api/v1/outbound", json={"to_name": "X"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EMPLOYEE_NOT_LINKED"


async def test_list_outbound_filters_by_status(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    created = (await client.post("/api/v1/outbound", json={"to_name": "A"})).json()["data"]
    await client.post("/api/v1/outbound", json={"to_name": "B"})

    await client.post(f"/api/v1/outbound/{created['id']}/shipped", json={})

    resp = await client.get("/api/v1/outbound?status=shipped")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == created["id"]


async def test_list_outbound_employee_role_allowed_and_scoped_to_self(client, db_session):
    """RC-FIX #4: GET /outbound previously 403'd for `employee` entirely;
    it must now be allowed, but server-side scoped to the caller's own
    applicant_employee_id (same self-check as get_outbound_item), not
    whatever `q`/filters the client happens to send."""
    await login_as(client, db_session, role=UserRole.admin)
    others = (await client.post("/api/v1/outbound", json={"to_name": "Others"})).json()["data"]

    user = await create_user(db_session, email="emp-list1@example.com", role=UserRole.employee)
    emp = await _make_employee(db_session, name="員工列表甲", user_id=user.id)
    await login(client, email="emp-list1@example.com")

    mine = (await client.post("/api/v1/outbound", json={"to_name": "Mine"})).json()["data"]
    assert mine["applicant_employee_id"] == emp.id

    resp = await client.get("/api/v1/outbound")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()["data"]}
    assert ids == {mine["id"]}
    assert others["id"] not in ids


async def test_list_outbound_employee_without_linked_record_gets_empty_list(client, db_session):
    await create_user(db_session, email="emp-list2@example.com", role=UserRole.employee)
    await login(client, email="emp-list2@example.com")

    resp = await client.get("/api/v1/outbound")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_get_outbound_employee_forbidden_for_others_request(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    created = (await client.post("/api/v1/outbound", json={"to_name": "A"})).json()["data"]

    user = await create_user(db_session, email="emp4@example.com", role=UserRole.employee)
    await _make_employee(db_session, name="員工乙", user_id=user.id)
    await login(client, email="emp4@example.com")

    resp = await client.get(f"/api/v1/outbound/{created['id']}")
    assert resp.status_code == 403


async def test_get_outbound_employee_allowed_for_own_request(client, db_session):
    dept = await _make_department(db_session, code="own")
    user = await create_user(db_session, email="emp5@example.com", role=UserRole.employee)
    emp = await _make_employee(db_session, name="員工丙", department_id=dept.id, user_id=user.id)
    await login(client, email="emp5@example.com")

    created = (await client.post("/api/v1/outbound", json={"to_name": "A"})).json()["data"]
    assert created["applicant_employee_id"] == emp.id

    resp = await client.get(f"/api/v1/outbound/{created['id']}")
    assert resp.status_code == 200


async def test_update_outbound_requires_write_role(client, db_session):
    user = await create_user(db_session, email="emp6@example.com", role=UserRole.employee)
    await _make_employee(db_session, name="員工丁", user_id=user.id)
    await login(client, email="emp6@example.com")
    created = (await client.post("/api/v1/outbound", json={"to_name": "A"})).json()["data"]

    resp = await client.patch(f"/api/v1/outbound/{created['id']}", json={"note": "x"})
    assert resp.status_code == 403


async def test_update_outbound_fields(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    created = (await client.post("/api/v1/outbound", json={"to_name": "A"})).json()["data"]

    resp = await client.patch(
        f"/api/v1/outbound/{created['id']}", json={"note": "updated", "cost": 123.45}
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["note"] == "updated"
    assert body["cost"] == 123.45


async def test_mark_shipped_success(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    created = (await client.post("/api/v1/outbound", json={"to_name": "A"})).json()["data"]

    resp = await client.post(
        f"/api/v1/outbound/{created['id']}/shipped", json={"tracking_no": "TRK-001"}
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["status"] == "shipped"
    assert body["tracking_no"] == "TRK-001"
    assert body["shipped_at"] is not None


async def test_mark_shipped_twice_conflicts(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    created = (await client.post("/api/v1/outbound", json={"to_name": "A"})).json()["data"]

    first = await client.post(f"/api/v1/outbound/{created['id']}/shipped", json={})
    assert first.status_code == 200

    second = await client.post(f"/api/v1/outbound/{created['id']}/shipped", json={})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "OUTBOUND_STATUS_INVALID"


async def test_mark_shipped_requires_write_role(client, db_session):
    user = await create_user(db_session, email="emp7@example.com", role=UserRole.employee)
    await _make_employee(db_session, name="員工戊", user_id=user.id)
    await login(client, email="emp7@example.com")
    created = (await client.post("/api/v1/outbound", json={"to_name": "A"})).json()["data"]

    resp = await client.post(f"/api/v1/outbound/{created['id']}/shipped", json={})
    assert resp.status_code == 403


async def test_mark_shipped_binds_pending_attachment(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    created = (await client.post("/api/v1/outbound", json={"to_name": "A"})).json()["data"]
    attachment = await _make_pending_attachment(db_session)

    resp = await client.post(
        f"/api/v1/outbound/{created['id']}/shipped", json={"attachment_id": attachment.id}
    )
    assert resp.status_code == 200

    await db_session.refresh(attachment)
    assert attachment.owner_type == AttachmentOwnerType.outbound_item
    assert attachment.owner_id == created["id"]


async def test_mark_shipped_rejects_already_linked_attachment(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    created = (await client.post("/api/v1/outbound", json={"to_name": "A"})).json()["data"]
    other = (await client.post("/api/v1/outbound", json={"to_name": "B"})).json()["data"]
    attachment = await _make_pending_attachment(db_session)

    ok = await client.post(
        f"/api/v1/outbound/{created['id']}/shipped", json={"attachment_id": attachment.id}
    )
    assert ok.status_code == 200

    resp = await client.post(
        f"/api/v1/outbound/{other['id']}/shipped", json={"attachment_id": attachment.id}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ATTACHMENT_ALREADY_LINKED"


async def test_mark_shipped_queues_notification_for_applicant(client, db_session):
    dept = await _make_department(db_session, code="notif")
    user = await create_user(db_session, email="emp8@example.com", role=UserRole.employee)
    emp = await _make_employee(db_session, name="員工己", department_id=dept.id, user_id=user.id)
    binding = NotificationBinding(
        employee_id=emp.id, channel=NotificationChannel.email, address="emp8@example.com"
    )
    db_session.add(binding)
    await db_session.commit()

    await login(client, email="emp8@example.com")
    created = (await client.post("/api/v1/outbound", json={"to_name": "A"})).json()["data"]

    await login_as(client, db_session, role=UserRole.counter, email="counter1@example.com")
    resp = await client.post(f"/api/v1/outbound/{created['id']}/shipped", json={})
    assert resp.status_code == 200

    await drain_background_notification_tasks()

    from sqlalchemy import select

    result = await db_session.execute(
        select(Notification).where(
            Notification.outbound_item_id == created["id"],
            Notification.template == NotificationTemplate.outbound_shipped,
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].employee_id == emp.id
    assert rows[0].mail_item_id is None


async def test_mark_shipped_publishes_webhook_event(client, db_session, monkeypatch):
    await login_as(client, db_session, role=UserRole.admin)
    endpoint = WebhookEndpoint(
        name="hook", url="https://example.com/hook", secret="s3cret",
        events=["outbound.shipped"], is_active=True,
    )
    db_session.add(endpoint)
    await db_session.commit()

    calls = []

    async def _fake_send_http(method, url, **kwargs):
        calls.append((method, url, kwargs.get("content")))
        return httpx.Response(200)

    import app.webhooks.publisher as publisher_module

    monkeypatch.setattr(publisher_module, "send_http", _fake_send_http)

    created = (await client.post("/api/v1/outbound", json={"to_name": "王小明"})).json()["data"]
    resp = await client.post(
        f"/api/v1/outbound/{created['id']}/shipped", json={"tracking_no": "T1"}
    )
    assert resp.status_code == 200

    await drain_background_notification_tasks()

    assert len(calls) == 1
    assert calls[0][1] == "https://example.com/hook"
    assert '"event":"outbound.shipped"' in calls[0][2]
    assert '"tracking_no":"T1"' in calls[0][2]


# --- M4-R1 contract: the list/detail UI renders these names directly -------


async def test_outbound_response_carries_display_names(client, db_session):
    """The outbound list shows 申請人/部門/承運商 by name. The backend used to
    return only the bare ids, so all three columns rendered 「—」 no matter what
    the data said -- and nothing caught it, because both sides' tests passed
    against their own assumptions."""
    from app.models.carrier import Carrier
    from app.models.enums import CarrierKind

    dept = await _make_department(db_session, code="fin")
    employee = await _make_employee(db_session, name="王小明", department_id=dept.id)
    carrier = Carrier(name="黑貓宅急便", slug="tcat", kind=CarrierKind.courier)
    db_session.add(carrier)
    await db_session.commit()
    await db_session.refresh(carrier)

    await login_as(client, db_session, role=UserRole.admin)
    created = await client.post(
        "/api/v1/outbound",
        json={
            "applicant_employee_id": employee.id,
            "department_id": dept.id,
            "carrier_id": carrier.id,
            "to_name": "李大同",
        },
    )
    assert created.status_code == 201
    body = created.json()["data"]
    assert body["applicant_name"] == "王小明"
    assert body["department_name"] == "Engineering"
    assert body["carrier_name"] == "黑貓宅急便"

    listed = await client.get("/api/v1/outbound")
    assert listed.status_code == 200
    row = listed.json()["data"][0]
    assert row["applicant_name"] == "王小明"
    assert row["department_name"] == "Engineering"
    assert row["carrier_name"] == "黑貓宅急便"

    detail = await client.get(f"/api/v1/outbound/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["applicant_name"] == "王小明"


async def test_outbound_display_names_null_when_unset(client, db_session):
    """A request with no applicant/department/carrier is legitimate -- the
    names are null rather than the endpoint erroring on the outer join."""
    await login_as(client, db_session, role=UserRole.admin)
    created = await client.post("/api/v1/outbound", json={"to_name": "李大同"})
    assert created.status_code == 201
    body = created.json()["data"]
    assert body["applicant_name"] is None
    assert body["department_name"] is None
    assert body["carrier_name"] is None
