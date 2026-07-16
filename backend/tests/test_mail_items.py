import re

from app.models.attachment import Attachment
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import AttachmentKind, AttachmentOwnerType, OcrStatus, UserRole
from app.models.ocr_job import OcrJob
from app.security.file_crypto import save_encrypted_file
from tests._helpers import create_user, login, login_as

ITEM_NO_RE = re.compile(r"^IN-\d{8}-\d{4}$")


async def _make_department(db_session, code="eng") -> Department:
    dept = Department(name="Engineering", code=code)
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


async def _make_employee(db_session, *, name="王小明", department_id=None, **kwargs) -> Employee:
    emp = Employee(name=name, aliases=[], department_id=department_id, **kwargs)
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


async def _make_pending_attachment(
    db_session, *, kind: AttachmentKind = AttachmentKind.label_photo
) -> Attachment:
    """A "pending" (self-owned, not yet confirmed into a record) attachment,
    matching what `POST /uploads` (app/api/v1/uploads.py) produces: created
    with a placeholder owner_id, then repointed to its own id once it has
    one -- see that module's docstring for why this self-owned marker
    exists.
    """
    stored = save_encrypted_file(b"fake-jpeg-bytes", subdir="mail_photos/pending", extension="jpg")
    attachment = Attachment(
        owner_type=AttachmentOwnerType.mail_item,
        owner_id="placeholder",
        kind=kind,
        file_path=stored["file_path"],
        sha256=stored["sha256"],
        mime="image/jpeg",
        size_bytes=stored["size_bytes"],
        width=40,
        height=30,
    )
    db_session.add(attachment)
    await db_session.commit()
    await db_session.refresh(attachment)
    attachment.owner_id = attachment.id
    await db_session.commit()
    await db_session.refresh(attachment)
    return attachment


async def _make_ocr_job(db_session, *, attachment_ids: list[str] | None = None) -> OcrJob:
    job = OcrJob(attachment_ids=attachment_ids or [], status=OcrStatus.succeeded)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


async def test_create_item_requires_counter_or_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)

    resp = await client.post("/api/v1/items", json={"recipient_name_raw": "王小明"})
    assert resp.status_code == 403


async def test_create_item_success_and_item_no_format(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    resp = await client.post("/api/v1/items", json={"recipient_name_raw": "王小明"})
    assert resp.status_code == 201
    body = resp.json()["data"]
    assert ITEM_NO_RE.match(body["item_no"])
    assert body["status"] == "received"
    assert body["direction"] == "inbound"
    assert body["mail_type"] == "parcel"


async def test_create_item_missing_recipient_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    resp = await client.post("/api/v1/items", json={})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_item_no_sequential_same_day(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    numbers = []
    for _ in range(3):
        resp = await client.post("/api/v1/items", json={"recipient_name_raw": "王小明"})
        assert resp.status_code == 201
        numbers.append(resp.json()["data"]["item_no"])

    prefix = numbers[0].rsplit("-", 1)[0]
    suffixes = [int(n.rsplit("-", 1)[1]) for n in numbers]
    assert all(n.startswith(prefix) for n in numbers)
    assert suffixes == sorted(suffixes)
    assert len(set(suffixes)) == 3


async def test_create_item_auto_fills_department_from_employee(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    dept = await _make_department(db_session)
    emp = await _make_employee(db_session, department_id=dept.id)

    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": emp.name, "recipient_employee_id": emp.id},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["department_id"] == dept.id


async def test_create_item_unknown_employee_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": "X", "recipient_employee_id": "nope"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EMPLOYEE_NOT_FOUND"


async def test_list_items_viewer_never_sees_confidential(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    await client.post(
        "/api/v1/items", json={"recipient_name_raw": "王小明", "is_confidential": True}
    )
    await client.post("/api/v1/items", json={"recipient_name_raw": "陳小華"})

    await create_user(db_session, email="viewer3@example.com", role=UserRole.viewer)
    await login(client, email="viewer3@example.com")

    resp = await client.get("/api/v1/items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 1
    assert all(item["is_confidential"] is False for item in body["data"])


async def test_list_items_employee_role_forbidden(client, db_session):
    await login_as(client, db_session, role=UserRole.employee)

    resp = await client.get("/api/v1/items")
    assert resp.status_code == 403


async def test_get_confidential_item_forbidden_for_viewer(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    created = (
        await client.post(
            "/api/v1/items", json={"recipient_name_raw": "王小明", "is_confidential": True}
        )
    ).json()["data"]

    await create_user(db_session, email="viewer4@example.com", role=UserRole.viewer)
    await login(client, email="viewer4@example.com")

    resp = await client.get(f"/api/v1/items/{created['id']}")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_get_confidential_item_allowed_for_counter_and_audited(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    created = (
        await client.post(
            "/api/v1/items", json={"recipient_name_raw": "王小明", "is_confidential": True}
        )
    ).json()["data"]

    resp = await client.get(f"/api/v1/items/{created['id']}")
    assert resp.status_code == 200

    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "mail_item.view_confidential")
    )
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].target_id == created["id"]


async def test_patch_item_cannot_change_status(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    created = (
        await client.post("/api/v1/items", json={"recipient_name_raw": "王小明"})
    ).json()["data"]

    resp = await client.patch(f"/api/v1/items/{created['id']}", json={"status": "picked_up"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_patch_item_updates_note(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    created = (
        await client.post("/api/v1/items", json={"recipient_name_raw": "王小明"})
    ).json()["data"]

    resp = await client.patch(
        f"/api/v1/items/{created['id']}", json={"note": "手寫備註"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["note"] == "手寫備註"


async def test_create_item_queues_notification_when_binding_exists(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    emp = await _make_employee(db_session)

    from app.models.enums import NotificationChannel
    from app.models.notification_binding import NotificationBinding

    binding = NotificationBinding(
        employee_id=emp.id, channel=NotificationChannel.line, address="U1234"
    )
    db_session.add(binding)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": emp.name, "recipient_employee_id": emp.id},
    )
    assert resp.status_code == 201
    item_id = resp.json()["data"]["id"]

    # M3-01: POST /items now also launches a background delivery attempt
    # (app.notify.worker) for the row this queues -- drain it before reading
    # the notifications table, same "drain before the next session touches
    # the DB" rule as the OCR background-task tests (see tests/_helpers.py).
    from tests._helpers import drain_background_notification_tasks

    await drain_background_notification_tasks()

    from sqlalchemy import select

    from app.models.notification import Notification

    result = await db_session.execute(
        select(Notification).where(Notification.mail_item_id == item_id)
    )
    notifications = result.scalars().all()
    assert len(notifications) == 1
    assert notifications[0].channel.value == "line"
    # No LINE channel access token is configured in this test environment,
    # so delivery exhausts all retries and dead-letters -- this is exactly
    # the "通知失敗清單" scenario the manual-resend endpoint exists for.
    assert notifications[0].status.value == "dead"
    assert notifications[0].retries == 5


async def test_create_item_skips_notification_without_binding(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    emp = await _make_employee(db_session)

    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": emp.name, "recipient_employee_id": emp.id},
    )
    item_id = resp.json()["data"]["id"]

    from sqlalchemy import select

    from app.models.notification import Notification

    result = await db_session.execute(
        select(Notification).where(Notification.mail_item_id == item_id)
    )
    assert result.scalars().all() == []


async def test_mail_item_create_writes_audit_log(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post("/api/v1/items", json={"recipient_name_raw": "王小明"})
    item_id = resp.json()["data"]["id"]

    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "mail_item.create", AuditLog.target_id == item_id
        )
    )
    assert len(result.scalars().all()) == 1


# M2-LINK: POST /items accepting ocr_job_id/attachment_ids so the OCR-confirm
# screen (frontend/src/pages/inbound/OcrConfirmPage.vue) can actually create
# the item it just drafted, instead of 422'ing on the extra="forbid" schema.


async def test_create_item_without_ocr_fields_is_unchanged(client, db_session):
    """Regression guard for the pre-M2-LINK behavior: omitting the two new
    optional fields entirely must still work exactly as before (manual
    entry, no photos) -- `ocr_job_id` reads back None and no attachment is
    touched."""
    await login_as(client, db_session, role=UserRole.counter)

    resp = await client.post("/api/v1/items", json={"recipient_name_raw": "王小明"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["ocr_job_id"] is None


async def test_create_item_binds_pending_attachments_and_ocr_job(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_pending_attachment(db_session, kind=AttachmentKind.extra_photo)
    job = await _make_ocr_job(db_session, attachment_ids=[attachment.id])

    resp = await client.post(
        "/api/v1/items",
        json={
            "recipient_name_raw": "王小明",
            "ocr_job_id": job.id,
            "attachment_ids": [attachment.id],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["ocr_job_id"] == job.id

    # `attachment` is already in `db_session`'s identity map (we created it
    # there), so a plain re-`SELECT` would just hand back the cached,
    # pre-bind Python object -- `refresh()` forces a real reload of this one
    # row instead (see M2-LINK completion notes: broad `expire_all()` here
    # triggers an unrelated SQLAlchemy/aiosqlite MissingGreenlet under this
    # suite's StaticPool single-connection setup; targeted `refresh()` does
    # not).
    await db_session.refresh(attachment)
    assert attachment.owner_type == AttachmentOwnerType.mail_item
    assert attachment.owner_id == body["id"]
    # M2-LINK: binding always normalizes kind to label_photo (the OCR-confirm
    # flow's photos are always of the shipping label), even if the upload
    # was originally tagged as a different kind.
    assert attachment.kind == AttachmentKind.label_photo


async def test_create_item_rejects_unknown_attachment_id(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": "王小明", "attachment_ids": ["does-not-exist"]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ATTACHMENT_NOT_FOUND"


async def test_create_item_rejects_attachment_already_linked_to_another_item(client, db_session):
    """A second confirm request must not be able to steal a photo that a
    first request already bound to its own item."""
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_pending_attachment(db_session)

    first = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": "王小明", "attachment_ids": [attachment.id]},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": "陳小華", "attachment_ids": [attachment.id]},
    )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "ATTACHMENT_ALREADY_LINKED"

    # The first item's binding must be untouched by the rejected second
    # attempt.
    await db_session.refresh(attachment)
    assert attachment.owner_id == first.json()["data"]["id"]


async def test_create_item_rejects_unknown_ocr_job_id(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": "王小明", "ocr_job_id": "does-not-exist"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OCR_JOB_NOT_FOUND"


async def test_create_item_rejects_invalid_attachment_leaves_no_item_created(client, db_session):
    """An invalid attachment_ids entry must reject the whole request -- no
    mail_item row (and no item_no burned) should be left behind."""
    await login_as(client, db_session, role=UserRole.counter)

    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": "王小明", "attachment_ids": ["nope"]},
    )
    assert resp.status_code == 400

    from sqlalchemy import select

    from app.models.mail_item import MailItem

    result = await db_session.execute(select(MailItem))
    assert result.scalars().all() == []


async def test_create_confidential_item_with_attachments(client, db_session):
    """機密件 + attachments: binding still succeeds, and the now-linked
    attachment correctly resolves as confidential (mirroring uploads.py's
    resolve_is_confidential) once it belongs to a confidential item."""
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_pending_attachment(db_session)

    resp = await client.post(
        "/api/v1/items",
        json={
            "recipient_name_raw": "王小明",
            "is_confidential": True,
            "attachment_ids": [attachment.id],
        },
    )
    assert resp.status_code == 201, resp.text
    item_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["is_confidential"] is True

    from sqlalchemy import select

    from app.models.mail_item import MailItem
    from app.services.confidential import resolve_is_confidential

    await db_session.refresh(attachment)
    assert attachment.owner_id == item_id

    item = (
        await db_session.execute(select(MailItem).where(MailItem.id == item_id))
    ).scalar_one()
    assert item.is_confidential is True
    assert await resolve_is_confidential(db_session, attachment) is True

    # A viewer must still be blocked from reading the now-linked photo back,
    # same as an unconfirmed/pending attachment would be.
    await create_user(db_session, email="viewer-confidential@example.com", role=UserRole.viewer)
    await login(client, email="viewer-confidential@example.com")
    get_resp = await client.get(f"/api/v1/uploads/{attachment.id}")
    assert get_resp.status_code == 403
