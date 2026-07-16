"""GET /api/v1/reports/summary -- aggregation correctness
(01-REQUIREMENTS.md section 4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.carrier import Carrier
from app.models.department import Department
from app.models.enums import (
    CarrierKind,
    MailStatus,
    MailType,
    OutboundStatus,
    Refrigeration,
    UserRole,
)
from app.models.mail_item import MailItem
from app.models.outbound_item import OutboundItem
from tests._helpers import login_as


async def _make_department(db_session, *, code, name="Dept") -> Department:
    dept = Department(name=name, code=code)
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


async def _make_carrier(db_session, *, slug, name="Carrier") -> Carrier:
    carrier = Carrier(name=name, slug=slug, kind=CarrierKind.courier)
    db_session.add(carrier)
    await db_session.commit()
    await db_session.refresh(carrier)
    return carrier


async def _make_mail_item(
    db_session, *, department_id=None, carrier_id=None, received_at, picked_up_at=None,
    status=MailStatus.received, seq,
) -> MailItem:
    item = MailItem(
        item_no=f"IN-REPORT-{seq:04d}",
        direction="inbound",
        mail_type=MailType.parcel,
        department_id=department_id,
        carrier_id=carrier_id,
        recipient_name_raw="X",
        received_at=received_at,
        picked_up_at=picked_up_at,
        status=status,
        refrigeration=Refrigeration.none,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _make_outbound_item(
    db_session, *, department_id=None, carrier_id=None, shipped_at, seq,
    status=OutboundStatus.shipped,
) -> OutboundItem:
    item = OutboundItem(
        item_no=f"OUT-REPORT-{seq:04d}",
        department_id=department_id,
        carrier_id=carrier_id,
        shipped_at=shipped_at,
        status=status,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def test_reports_requires_read_role(client, db_session):
    from tests._helpers import create_user, login

    await create_user(db_session, email="empx@example.com", role=UserRole.employee)
    await login(client, email="empx@example.com")

    resp = await client.get("/api/v1/reports/summary")
    assert resp.status_code == 403


async def test_reports_rejects_invalid_group_by(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.get("/api/v1/reports/summary?group_by=bogus")
    assert resp.status_code == 400


async def test_reports_group_by_day_counts(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    base = datetime(2026, 1, 10, 9, 0, tzinfo=timezone.utc)
    await _make_mail_item(db_session, received_at=base, seq=1)
    await _make_mail_item(db_session, received_at=base + timedelta(hours=1), seq=2)
    await _make_mail_item(db_session, received_at=base + timedelta(days=1), seq=3)

    resp = await client.get(
        "/api/v1/reports/summary?group_by=day"
        "&from=2026-01-01T00:00:00Z&to=2026-01-31T00:00:00Z"
    )
    assert resp.status_code == 200
    rows = {r["key"]: r for r in resp.json()["data"]["rows"]}
    assert rows["2026-01-10"]["received_count"] == 2
    assert rows["2026-01-11"]["received_count"] == 1
    assert resp.json()["data"]["totals"]["received_count"] == 3


async def test_reports_group_by_department_with_names(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    dept_a = await _make_department(db_session, code="dept-a", name="部門A")
    dept_b = await _make_department(db_session, code="dept-b", name="部門B")
    now = datetime.now(timezone.utc)
    await _make_mail_item(db_session, department_id=dept_a.id, received_at=now, seq=10)
    await _make_mail_item(db_session, department_id=dept_a.id, received_at=now, seq=11)
    await _make_mail_item(db_session, department_id=dept_b.id, received_at=now, seq=12)
    await _make_mail_item(db_session, department_id=None, received_at=now, seq=13)

    resp = await client.get("/api/v1/reports/summary?group_by=department")
    assert resp.status_code == 200
    rows = {r["key"]: r for r in resp.json()["data"]["rows"]}
    assert rows[dept_a.id]["received_count"] == 2
    assert rows[dept_a.id]["label"] == "部門A"
    assert rows[dept_b.id]["received_count"] == 1
    assert rows["unassigned"]["received_count"] == 1
    assert rows["unassigned"]["label"] == "未分配"


async def test_reports_group_by_carrier_with_outbound_shipped_count(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    carrier = await _make_carrier(db_session, slug="tcat", name="黑貓")
    now = datetime.now(timezone.utc)
    await _make_mail_item(db_session, carrier_id=carrier.id, received_at=now, seq=20)
    await _make_outbound_item(db_session, carrier_id=carrier.id, shipped_at=now, seq=21)
    await _make_outbound_item(db_session, carrier_id=carrier.id, shipped_at=now, seq=22)
    # A pending (not shipped) outbound item must not count toward
    # outbound_shipped_count.
    await _make_outbound_item(
        db_session, carrier_id=carrier.id, shipped_at=None, seq=23, status=OutboundStatus.pending
    )

    resp = await client.get("/api/v1/reports/summary?group_by=carrier")
    assert resp.status_code == 200
    rows = {r["key"]: r for r in resp.json()["data"]["rows"]}
    assert rows[carrier.id]["received_count"] == 1
    assert rows[carrier.id]["outbound_shipped_count"] == 2
    assert resp.json()["data"]["totals"]["outbound_shipped_count"] == 2


async def test_reports_avg_pickup_hours_and_unclaimed(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    now = datetime.now(timezone.utc)
    received1 = now - timedelta(hours=10)
    picked1 = received1 + timedelta(hours=2)  # 7200s = 2h
    received2 = now - timedelta(hours=8)
    picked2 = received2 + timedelta(hours=4)  # 14400s = 4h

    await _make_mail_item(
        db_session, received_at=received1, picked_up_at=picked1,
        status=MailStatus.picked_up, seq=30,
    )
    await _make_mail_item(
        db_session, received_at=received2, picked_up_at=picked2,
        status=MailStatus.picked_up, seq=31,
    )
    await _make_mail_item(
        db_session, received_at=now - timedelta(hours=1), seq=32, status=MailStatus.unclaimed
    )

    resp = await client.get("/api/v1/reports/summary?group_by=day")
    assert resp.status_code == 200
    body = resp.json()["data"]
    totals = body["totals"]
    assert totals["picked_up_count"] == 2
    # avg of (2h, 4h) == 3h. RC-FIX #3: reports now expose hours, not raw
    # seconds -- avg_pickup_seconds must not appear in the response at all.
    assert totals["avg_pickup_hours"] == (2 + 4) / 2
    assert "avg_pickup_seconds" not in totals
    assert totals["unclaimed_count"] == 1

    # Same unit fix must apply per-row, not just totals.
    for row in body["rows"]:
        assert "avg_pickup_seconds" not in row
        if row["picked_up_count"]:
            assert row["avg_pickup_hours"] is not None
