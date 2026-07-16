"""Every timestamp this API emits must be an *offset-bearing* UTC ISO string.

Why this file exists: `DateTime(timezone=True)` silently drops tzinfo on
SQLite (the driver has nowhere to put an offset). That produced two real,
user-visible defects, both fixed by `app.models.types.UtcDateTime`:

  * a UTC value read back naive serialized as "2026-07-16T06:30:05" with no
    offset. JavaScript parses an offset-less date-time as **local** time, so
    the browser rendered every timestamp 8 hours early in Taipei.
  * an aware "+08:00" datetime from an API client was stored as its bare
    local wall clock and thereafter treated as UTC -- 8 hours wrong *in the
    database*, which then poisoned date filters and reports.

These tests pin the contract at both ends so neither can regress silently.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.models.enums import MailStatus, MailType, Refrigeration, UserRole
from app.models.mail_item import MailItem
from tests._helpers import login_as

TAIPEI = timezone(timedelta(hours=8))

# "+00:00" or "Z" -- what matters is that an offset is present at all.
def _has_utc_offset(iso: str) -> bool:
    return iso.endswith("+00:00") or iso.endswith("Z")


async def test_stored_aware_local_time_is_normalized_to_utc(db_session):
    """A client sending 14:30:05+08:00 must land in the DB as 06:30:05 UTC,
    not as the bare wall clock 14:30:05."""
    item = MailItem(
        item_no="TZ-1",
        direction="inbound",
        mail_type=MailType.letter,
        received_at=datetime(2026, 7, 16, 14, 30, 5, tzinfo=TAIPEI),
        status=MailStatus.received,
        is_confidential=False,
        is_cod=False,
        refrigeration=Refrigeration.none,
    )
    db_session.add(item)
    await db_session.commit()

    raw = (
        await db_session.execute(
            text("SELECT received_at FROM mail_items WHERE item_no = 'TZ-1'")
        )
    ).scalar()
    assert str(raw).startswith("2026-07-16 06:30:05")


async def test_value_read_back_is_utc_aware(db_session):
    item = MailItem(
        item_no="TZ-2",
        direction="inbound",
        mail_type=MailType.letter,
        received_at=datetime(2026, 7, 16, 6, 30, 5, tzinfo=timezone.utc),
        status=MailStatus.received,
        is_confidential=False,
        is_cod=False,
        refrigeration=Refrigeration.none,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    assert item.received_at.tzinfo is not None
    assert item.received_at == datetime(2026, 7, 16, 6, 30, 5, tzinfo=timezone.utc)
    assert item.received_at.isoformat() == "2026-07-16T06:30:05+00:00"
    # Server-set columns go through the same decorator.
    assert item.created_at.tzinfo is not None


async def test_item_api_emits_offset_bearing_timestamps(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post(
        "/api/v1/items",
        json={"mail_type": "letter", "recipient_name_raw": "王小明"},
    )
    assert resp.status_code == 201
    created = resp.json()["data"]

    for field in ("received_at", "created_at", "updated_at"):
        assert _has_utc_offset(created[field]), f"{field} has no UTC offset: {created[field]!r}"

    detail = await client.get(f"/api/v1/items/{created['id']}")
    assert detail.status_code == 200
    assert _has_utc_offset(detail.json()["data"]["received_at"])

    listed = await client.get("/api/v1/items")
    assert listed.status_code == 200
    assert _has_utc_offset(listed.json()["data"][0]["received_at"])


async def test_client_supplied_offset_survives_round_trip_through_api(client, db_session):
    """The end-to-end version of the DB test: what the client sends as
    +08:00 comes back as the same *instant* expressed in UTC."""
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post(
        "/api/v1/items",
        json={
            "mail_type": "letter",
            "recipient_name_raw": "王小明",
            "received_at": "2026-07-16T14:30:05+08:00",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["received_at"] == "2026-07-16T06:30:05+00:00"
