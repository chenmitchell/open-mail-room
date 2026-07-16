"""GET /api/v1/exports/items.csv, GET /api/v1/exports/outbound.csv --
03-API-SPEC.md section 2 / 01-REQUIREMENTS.md section 4 "匯出 CSV".

Both endpoints stream the CSV body (bounded memory regardless of row count)
and:
- prefix a UTF-8 BOM so Excel on Windows opens 繁體中文 without mangling it,
- run every cell through escape_for_csv_export before writing it.

RBAC note: 03-API-SPEC.md lists these under "scopes: reports:read" (an
API-key bearer scope). This codebase has no bearer/API-key authentication
path wired into RBAC yet -- see the M4-01 report for this deviation. Gated
the same way every other session-authenticated report/list endpoint is:
role membership (admin/counter/viewer), mirroring
app.api.v1.mail_items.READ_ROLES.
"""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.mail_items import READ_ROLES
from app.db import get_session
from app.models.carrier import Carrier
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import MailStatus, OutboundStatus, UserRole
from app.models.mail_item import MailItem
from app.models.outbound_item import OutboundItem
from app.models.user import User
from app.security.csrf import require_csrf
from app.security.rbac import require_role
from app.services.audit import record_audit
from app.util.csv_safety import escape_for_csv_export

router = APIRouter(prefix="/exports", tags=["exports"], dependencies=[Depends(require_csrf)])

_BOM = "﻿"

ITEMS_HEADER = [
    "item_no", "tracking_no", "carrier", "mail_type", "sender_name", "sender_org",
    "recipient_name", "department", "status", "is_confidential", "is_cod", "cod_amount",
    "refrigeration", "received_at", "notified_at", "picked_up_at", "picked_up_by_name",
    "pickup_method", "note",
]

OUTBOUND_HEADER = [
    "item_no", "applicant_name", "department", "to_name", "to_org", "carrier", "tracking_no",
    "status", "cost", "payment", "shipped_at", "note",
]


def _row_line(values: list) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([escape_for_csv_export(v) if v is not None else "" for v in values])
    return buf.getvalue()


async def _stream_items_csv(
    session: AsyncSession, *, q, status, carrier_id, department_id, date_from, date_to,
    confidential, include_confidential_rows: bool,
) -> AsyncGenerator[str, None]:
    yield _BOM
    yield _row_line(ITEMS_HEADER)

    stmt = (
        select(MailItem, Carrier.name, Department.name, Employee.name)
        .outerjoin(Carrier, MailItem.carrier_id == Carrier.id)
        .outerjoin(Department, MailItem.department_id == Department.id)
        .outerjoin(Employee, MailItem.recipient_employee_id == Employee.id)
    )
    conditions = []
    if q:
        like = f"%{q}%"
        conditions.append(
            (MailItem.item_no.ilike(like))
            | (MailItem.tracking_no.ilike(like))
            | (MailItem.sender_name.ilike(like))
            | (MailItem.recipient_name_raw.ilike(like))
        )
    if status:
        conditions.append(MailItem.status == status)
    if carrier_id:
        conditions.append(MailItem.carrier_id == carrier_id)
    if department_id:
        conditions.append(MailItem.department_id == department_id)
    if date_from:
        conditions.append(MailItem.received_at >= date_from)
    if date_to:
        conditions.append(MailItem.received_at <= date_to)
    if not include_confidential_rows:
        conditions.append(MailItem.is_confidential.is_(False))
    elif confidential is not None:
        conditions.append(MailItem.is_confidential == confidential)
    for cond in conditions:
        stmt = stmt.where(cond)
    stmt = stmt.order_by(MailItem.received_at.desc())

    result = await session.stream(stmt)
    async for item, carrier_name, department_name, employee_name in result:
        yield _row_line([
            item.item_no, item.tracking_no, carrier_name, item.mail_type.value,
            item.sender_name, item.sender_org, employee_name or item.recipient_name_raw,
            department_name, item.status.value, str(item.is_confidential), str(item.is_cod),
            str(item.cod_amount) if item.cod_amount is not None else None,
            item.refrigeration.value,
            item.received_at.isoformat() if item.received_at else None,
            item.notified_at.isoformat() if item.notified_at else None,
            item.picked_up_at.isoformat() if item.picked_up_at else None,
            item.picked_up_by_name,
            item.pickup_method.value if item.pickup_method else None,
            item.note,
        ])


async def _stream_outbound_csv(
    session: AsyncSession, *, q, status, carrier_id, department_id, date_from, date_to,
) -> AsyncGenerator[str, None]:
    yield _BOM
    yield _row_line(OUTBOUND_HEADER)

    stmt = (
        select(OutboundItem, Employee.name, Department.name, Carrier.name)
        .outerjoin(Employee, OutboundItem.applicant_employee_id == Employee.id)
        .outerjoin(Department, OutboundItem.department_id == Department.id)
        .outerjoin(Carrier, OutboundItem.carrier_id == Carrier.id)
    )
    conditions = []
    if q:
        like = f"%{q}%"
        conditions.append(
            (OutboundItem.item_no.ilike(like))
            | (OutboundItem.tracking_no.ilike(like))
            | (OutboundItem.to_name.ilike(like))
        )
    if status:
        conditions.append(OutboundItem.status == status)
    if carrier_id:
        conditions.append(OutboundItem.carrier_id == carrier_id)
    if department_id:
        conditions.append(OutboundItem.department_id == department_id)
    if date_from:
        conditions.append(OutboundItem.created_at >= date_from)
    if date_to:
        conditions.append(OutboundItem.created_at <= date_to)
    for cond in conditions:
        stmt = stmt.where(cond)
    stmt = stmt.order_by(OutboundItem.created_at.desc())

    result = await session.stream(stmt)
    async for item, applicant_name, department_name, carrier_name in result:
        yield _row_line([
            item.item_no, applicant_name, department_name, item.to_name, item.to_org,
            carrier_name, item.tracking_no, item.status.value,
            str(item.cost) if item.cost is not None else None,
            item.payment.value if item.payment else None,
            item.shipped_at.isoformat() if item.shipped_at else None,
            item.note,
        ])


@router.get("/items.csv")
async def export_items_csv(
    request: Request,
    q: str | None = None,
    status: MailStatus | None = None,
    carrier_id: str | None = None,
    department_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    confidential: bool | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*READ_ROLES)),
):
    include_confidential_rows = user.role != UserRole.viewer

    if include_confidential_rows:
        await record_audit(
            session, request=request, actor=user, action="mail_item.export_csv",
            target_type="mail_item", target_id=None,
            diff={"filters": {
                "q": q, "status": status.value if status else None, "carrier_id": carrier_id,
                "department_id": department_id, "confidential": confidential,
            }},
        )
        await session.commit()

    generator = _stream_items_csv(
        session, q=q, status=status, carrier_id=carrier_id, department_id=department_id,
        date_from=date_from, date_to=date_to, confidential=confidential,
        include_confidential_rows=include_confidential_rows,
    )
    return StreamingResponse(
        generator, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="items.csv"'},
    )


@router.get("/outbound.csv")
async def export_outbound_csv(
    q: str | None = None,
    status: OutboundStatus | None = None,
    carrier_id: str | None = None,
    department_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*READ_ROLES)),
):
    generator = _stream_outbound_csv(
        session, q=q, status=status, carrier_id=carrier_id, department_id=department_id,
        date_from=date_from, date_to=date_to,
    )
    return StreamingResponse(
        generator, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="outbound.csv"'},
    )
