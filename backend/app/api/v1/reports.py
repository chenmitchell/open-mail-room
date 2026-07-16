"""GET /api/v1/reports/summary -- 03-API-SPEC.md section 2 "管理":

    GET /reports/summary?from=&to=&group_by=department|carrier|day

01-REQUIREMENTS.md section 4: "報表:每日/每月件量、各部門件量、平均領取
時間、滯留清單、各承運商佔比" plus the M4-01 task brief's addition of
"交寄量" (outbound shipped volume) alongside the inbound metrics.

Performance note (task brief: "aggregate SQL 不要 N+1"): this endpoint issues
a small, fixed number of queries regardless of how many groups the report
ends up having -- one SELECT of the raw (dimension, received_at,
picked_up_at, status) tuples for mail_items in the date window, one sibling
SELECT for outbound_items, and (only when group_by needs names) one SELECT
each for the full departments/carriers tables to build an id->name lookup.
Grouping/aggregation across those rows happens in Python. This is
deliberately *not* a per-group query loop (the N+1 shape the brief warns
against); for very large date windows a future iteration could push the
grouping into SQL (`GROUP BY` + `func.date(...)`, portable across
SQLite/PostgreSQL) if profiling shows the Python-side pass is the
bottleneck.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok
from app.api.v1.mail_items import READ_ROLES
from app.db import get_session
from app.models.carrier import Carrier
from app.models.department import Department
from app.models.enums import MailStatus, OutboundStatus
from app.models.mail_item import MailItem
from app.models.outbound_item import OutboundItem
from app.models.user import User
from app.security.csrf import require_csrf
from app.security.rbac import require_role

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_csrf)])

_VALID_GROUP_BY = {"department", "carrier", "day"}
_UNASSIGNED_KEY = "unassigned"


def _day_key(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.date().isoformat()


def _dimension_key(
    group_by: str, *, department_id: str | None, carrier_id: str | None, at: datetime | None
) -> str | None:
    if group_by == "day":
        return _day_key(at)
    if group_by == "department":
        return department_id or _UNASSIGNED_KEY
    return carrier_id or _UNASSIGNED_KEY  # group_by == "carrier"


class _MailStats:
    __slots__ = (
        "received",
        "picked_up",
        "pickup_seconds_total",
        "pickup_seconds_count",
        "unclaimed",
    )

    def __init__(self) -> None:
        self.received = 0
        self.picked_up = 0
        self.pickup_seconds_total = 0.0
        self.pickup_seconds_count = 0
        self.unclaimed = 0


async def _name_lookup(session: AsyncSession, group_by: str) -> dict[str, str]:
    if group_by == "department":
        rows = (await session.execute(select(Department.id, Department.name))).all()
        return {row[0]: row[1] for row in rows}
    if group_by == "carrier":
        rows = (await session.execute(select(Carrier.id, Carrier.name))).all()
        return {row[0]: row[1] for row in rows}
    return {}


def _default_label(group_by: str) -> str:
    if group_by == "department":
        return "未分配"
    if group_by == "carrier":
        return "未指定"
    return ""


@router.get("/summary")
async def report_summary(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    group_by: str = Query(default="day"),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*READ_ROLES)),
):
    if group_by not in _VALID_GROUP_BY:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "group_by must be one of: department, carrier, day",
            },
        )

    mail_stmt = select(
        MailItem.department_id,
        MailItem.carrier_id,
        MailItem.received_at,
        MailItem.picked_up_at,
        MailItem.status,
    )
    if from_:
        mail_stmt = mail_stmt.where(MailItem.received_at >= from_)
    if to:
        mail_stmt = mail_stmt.where(MailItem.received_at <= to)
    mail_rows = (await session.execute(mail_stmt)).all()

    outbound_stmt = select(
        OutboundItem.department_id, OutboundItem.carrier_id, OutboundItem.shipped_at
    ).where(OutboundItem.status == OutboundStatus.shipped)
    if from_:
        outbound_stmt = outbound_stmt.where(OutboundItem.shipped_at >= from_)
    if to:
        outbound_stmt = outbound_stmt.where(OutboundItem.shipped_at <= to)
    outbound_rows = (await session.execute(outbound_stmt)).all()

    stats: dict[str, _MailStats] = {}
    for department_id, carrier_id, received_at, picked_up_at, status in mail_rows:
        key = _dimension_key(
            group_by, department_id=department_id, carrier_id=carrier_id, at=received_at
        )
        if key is None:
            continue
        bucket = stats.setdefault(key, _MailStats())
        bucket.received += 1
        if picked_up_at is not None:
            bucket.picked_up += 1
            bucket.pickup_seconds_total += (picked_up_at - received_at).total_seconds()
            bucket.pickup_seconds_count += 1
        if status == MailStatus.unclaimed:
            bucket.unclaimed += 1

    outbound_counts: dict[str, int] = {}
    for department_id, carrier_id, shipped_at in outbound_rows:
        key = _dimension_key(
            group_by, department_id=department_id, carrier_id=carrier_id, at=shipped_at
        )
        if key is None:
            continue
        outbound_counts[key] = outbound_counts.get(key, 0) + 1

    names = await _name_lookup(session, group_by)
    default_label = _default_label(group_by)

    all_keys = sorted(set(stats.keys()) | set(outbound_counts.keys()))
    rows: list[dict[str, Any]] = []
    total_received = 0
    total_picked_up = 0
    total_pickup_seconds = 0.0
    total_pickup_count = 0
    total_unclaimed = 0
    total_outbound_shipped = 0

    for key in all_keys:
        bucket = stats.get(key, _MailStats())
        outbound_shipped_count = outbound_counts.get(key, 0)
        avg_pickup_hours = (
            bucket.pickup_seconds_total / bucket.pickup_seconds_count / 3600
            if bucket.pickup_seconds_count
            else None
        )
        if group_by == "day":
            label = key
        else:
            label = names.get(key, default_label if key == _UNASSIGNED_KEY else key)

        rows.append(
            {
                "key": key,
                "label": label,
                "received_count": bucket.received,
                "picked_up_count": bucket.picked_up,
                "avg_pickup_hours": avg_pickup_hours,
                "unclaimed_count": bucket.unclaimed,
                "outbound_shipped_count": outbound_shipped_count,
            }
        )
        total_received += bucket.received
        total_picked_up += bucket.picked_up
        total_pickup_seconds += bucket.pickup_seconds_total
        total_pickup_count += bucket.pickup_seconds_count
        total_unclaimed += bucket.unclaimed
        total_outbound_shipped += outbound_shipped_count

    totals = {
        "received_count": total_received,
        "picked_up_count": total_picked_up,
        "avg_pickup_hours": (
            total_pickup_seconds / total_pickup_count / 3600 if total_pickup_count else None
        ),
        "unclaimed_count": total_unclaimed,
        "outbound_shipped_count": total_outbound_shipped,
    }

    return ok(
        {
            "from": from_.isoformat() if from_ else None,
            "to": to.isoformat() if to else None,
            "group_by": group_by,
            "rows": rows,
            "totals": totals,
        }
    )
