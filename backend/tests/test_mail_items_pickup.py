import base64
import struct

from app.models.employee import Employee
from app.models.enums import MailStatus, UserRole
from tests._helpers import login_as

# A well-known minimal valid 1x1 transparent PNG.
VALID_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
INVALID_PNG_B64 = base64.b64encode(b"this is not a png file").decode()


def _fake_png_with_dimensions(width: int, height: int) -> bytes:
    """A structurally-plausible-enough PNG (magic bytes + IHDR chunk with
    the given dimensions) for exercising validate_png's dimension check --
    not a real renderable image, just enough bytes for the header parser."""
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0d"
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


HUGE_DIMENSIONS_PNG_B64 = base64.b64encode(_fake_png_with_dimensions(50_000, 50_000)).decode()


async def _make_employee(db_session, *, name="王小明", pickup_code="CODE1234") -> Employee:
    emp = Employee(name=name, aliases=[], pickup_code=pickup_code)
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


async def _create_item(client, *, recipient_employee_id=None, recipient_name_raw="王小明"):
    payload = {"recipient_name_raw": recipient_name_raw}
    if recipient_employee_id:
        payload["recipient_employee_id"] = recipient_employee_id
    resp = await client.post("/api/v1/items", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_pickup_requires_counter_or_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    item = await _create_item(client)

    from tests._helpers import create_user, login

    await create_user(db_session, email="emp1@example.com", role=UserRole.employee)
    await login(client, email="emp1@example.com")

    resp = await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={"method": "pickup_code", "picked_up_by_name": "王小明", "pickup_code": "x"},
    )
    assert resp.status_code == 403


async def test_pickup_via_pickup_code_success(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    emp = await _make_employee(db_session)
    item = await _create_item(client, recipient_employee_id=emp.id, recipient_name_raw=emp.name)

    resp = await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={
            "method": "pickup_code",
            "picked_up_by_name": "王小明",
            "pickup_code": "CODE1234",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["status"] == "picked_up"
    assert body["pickup_method"] == "pickup_code"
    assert body["picked_up_by_name"] == "王小明"
    assert body["picked_up_at"] is not None


async def test_pickup_via_pickup_code_wrong_code_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    emp = await _make_employee(db_session)
    item = await _create_item(client, recipient_employee_id=emp.id, recipient_name_raw=emp.name)

    resp = await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={
            "method": "pickup_code",
            "picked_up_by_name": "王小明",
            "pickup_code": "WRONGCODE",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PICKUP_CODE_INVALID"


async def test_pickup_via_pickup_code_no_recipient_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    item = await _create_item(client)  # no recipient_employee_id

    resp = await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={"method": "pickup_code", "picked_up_by_name": "X", "pickup_code": "ANYTHING"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PICKUP_CODE_INVALID"


async def test_pickup_via_signature_stores_encrypted_attachment(
    client, db_session, tmp_path, monkeypatch
):
    from app.config import reset_settings_cache

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    reset_settings_cache()
    try:
        await login_as(client, db_session, role=UserRole.counter)
        item = await _create_item(client)

        resp = await client.post(
            f"/api/v1/items/{item['id']}/pickup",
            json={
                "method": "signature",
                "picked_up_by_name": "代領人",
                "signature_png_base64": VALID_PNG_B64,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["status"] == "picked_up"
        assert body["pickup_method"] == "signature"

        from sqlalchemy import select

        from app.models.attachment import Attachment

        result = await db_session.execute(
            select(Attachment).where(Attachment.owner_id == item["id"])
        )
        attachments = result.scalars().all()
        assert len(attachments) == 1
        attachment = attachments[0]
        assert attachment.kind.value == "pickup_signature"
        assert attachment.mime == "image/png"

        stored_path = tmp_path / attachment.file_path
        assert stored_path.exists()
        raw_on_disk = stored_path.read_bytes()
        plaintext_png = base64.b64decode(VALID_PNG_B64)
        # Must not be stored as plaintext PNG bytes at rest.
        assert raw_on_disk != plaintext_png
        assert not raw_on_disk.startswith(b"\x89PNG")
    finally:
        monkeypatch.delenv("UPLOAD_DIR", raising=False)
        reset_settings_cache()


async def test_pickup_via_signature_invalid_png_rejected(client, db_session, tmp_path, monkeypatch):
    from app.config import reset_settings_cache

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    reset_settings_cache()
    try:
        await login_as(client, db_session, role=UserRole.counter)
        item = await _create_item(client)

        resp = await client.post(
            f"/api/v1/items/{item['id']}/pickup",
            json={
                "method": "signature",
                "picked_up_by_name": "代領人",
                "signature_png_base64": INVALID_PNG_B64,
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "UPLOAD_BAD_TYPE"
    finally:
        monkeypatch.delenv("UPLOAD_DIR", raising=False)
        reset_settings_cache()


async def test_pickup_via_signature_oversized_dimensions_rejected(
    client, db_session, tmp_path, monkeypatch
):
    """M1-R1 suggestion: validate_png must reject a PNG whose IHDR chunk
    claims dimensions past MAX_PNG_DIMENSION, not just check magic bytes."""
    from app.config import reset_settings_cache

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    reset_settings_cache()
    try:
        await login_as(client, db_session, role=UserRole.counter)
        item = await _create_item(client)

        resp = await client.post(
            f"/api/v1/items/{item['id']}/pickup",
            json={
                "method": "signature",
                "picked_up_by_name": "代領人",
                "signature_png_base64": HUGE_DIMENSIONS_PNG_B64,
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "UPLOAD_BAD_TYPE"
    finally:
        monkeypatch.delenv("UPLOAD_DIR", raising=False)
        reset_settings_cache()


async def test_conditional_transition_race_only_one_racer_wins(client, db_session):
    """M1-R1 blocking #5: the old read -> assert -> write flow had no
    atomicity, so two concurrent pickup requests for the same item, both
    having read the same pre-write status, could both pass the status check
    and both "succeed". `_conditional_transition` closes that gap by folding
    the status check into the UPDATE's WHERE clause, so the database itself
    is the single arbiter of who "wins".

    This is exercised directly against `_conditional_transition` (rather
    than via two literal concurrent HTTP requests through `asyncio.gather`)
    because the test suite's SQLite engine uses a StaticPool -- a single
    shared physical connection for the whole process (see app/db.py) so
    tests can see each other's writes without a real multi-connection
    database. That's fine for the sequential access every other test in
    this suite does, but two *actually concurrent* async sessions sharing
    one physical SQLite connection can step on each other's
    transaction/rollback state in ways a real database with independent
    connections never would -- which would make an asyncio.gather-based
    version of this test flaky/wrong for reasons that have nothing to do
    with whether the production code's atomicity guarantee is correct.
    Calling the same primitive `pickup_item`/`return_item`/`forward_item`
    all delegate to, twice, against the same pre-fetched `item` object
    (simulating two racers who both read the row before either wrote),
    proves the guarantee deterministically: only the first call's UPDATE
    can ever match the WHERE clause.
    """
    from sqlalchemy import select

    from app.api.v1.mail_items import _conditional_transition
    from app.models.mail_item import MailItem

    await login_as(client, db_session, role=UserRole.counter)
    emp = await _make_employee(db_session)
    created = await _create_item(client, recipient_employee_id=emp.id, recipient_name_raw=emp.name)

    result = await db_session.execute(select(MailItem).where(MailItem.id == created["id"]))
    item = result.scalar_one()
    assert item.status.value == "received"

    # Both "racers" hold the same pre-write snapshot of `item` (status still
    # "received" in memory for both) -- exactly what two concurrent request
    # handlers would each have after their own `_get_or_404` read.
    won_first = await _conditional_transition(
        db_session, item, values={"status": MailStatus.picked_up}
    )
    won_second = await _conditional_transition(
        db_session, item, values={"status": MailStatus.picked_up}
    )
    await db_session.commit()

    assert won_first is True
    assert won_second is False

    await db_session.refresh(item)
    assert item.status == MailStatus.picked_up


async def test_pickup_already_picked_item_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    emp = await _make_employee(db_session)
    item = await _create_item(client, recipient_employee_id=emp.id, recipient_name_raw=emp.name)

    first = await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={"method": "pickup_code", "picked_up_by_name": "A", "pickup_code": "CODE1234"},
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={"method": "pickup_code", "picked_up_by_name": "A", "pickup_code": "CODE1234"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ITEM_ALREADY_PICKED"


async def test_pickup_missing_picked_up_by_name_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    item = await _create_item(client)

    resp = await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={"method": "pickup_code", "picked_up_by_name": "", "pickup_code": "x"},
    )
    assert resp.status_code == 422


async def test_return_item_success(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    item = await _create_item(client)

    resp = await client.post(f"/api/v1/items/{item['id']}/return", json={"note": "收件人已離職"})
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["status"] == "returned"
    assert "收件人已離職" in body["note"]


async def test_return_already_picked_item_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    emp = await _make_employee(db_session)
    item = await _create_item(client, recipient_employee_id=emp.id, recipient_name_raw=emp.name)
    await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={"method": "pickup_code", "picked_up_by_name": "A", "pickup_code": "CODE1234"},
    )

    resp = await client.post(f"/api/v1/items/{item['id']}/return", json={})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ITEM_ALREADY_PICKED"


async def test_forward_item_success(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    item = await _create_item(client)

    resp = await client.post(
        f"/api/v1/items/{item['id']}/forward",
        json={"forward_to": "台北分公司", "note": "原收件人已調部門"},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["status"] == "forwarded"
    assert "台北分公司" in body["note"]


async def test_forward_from_returned_status_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    item = await _create_item(client)
    await client.post(f"/api/v1/items/{item['id']}/return", json={})

    resp = await client.post(f"/api/v1/items/{item['id']}/forward", json={"forward_to": "X"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ITEM_STATUS_INVALID"


async def test_pickup_writes_audit_log(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    emp = await _make_employee(db_session)
    item = await _create_item(client, recipient_employee_id=emp.id, recipient_name_raw=emp.name)

    await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={"method": "pickup_code", "picked_up_by_name": "A", "pickup_code": "CODE1234"},
    )

    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "mail_item.pickup", AuditLog.target_id == item["id"]
        )
    )
    logs = result.scalars().all()
    assert len(logs) == 1
