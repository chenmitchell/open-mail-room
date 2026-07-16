"""Builds the `03-API-SPEC.md` section 3 event payload:

    {
      "event": "item.received",
      "id": "evt_...",
      "occurred_at": "2026-07-09T10:00:00+08:00",
      "data": { "item_no": ..., "tracking_no": ..., "carrier": ...,
                "recipient": {...}, "status": ..., "confidential": bool }
    }

Confidential items hide `sender` and photo links (there are no photo links
in this payload shape at all today, so the sender omission is the whole of
it -- see the `sender` key below, which is entirely absent rather than
present-and-empty, so a receiver can't distinguish "no sender recorded"
from "sender withheld").
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.carrier import Carrier
from app.models.department import Department
from app.models.employee import Employee
from app.models.mail_item import MailItem
from app.models.outbound_item import OutboundItem
from app.util.uuid7 import uuid7_str


async def build_event_payload(
    session,
    *,
    event: str,
    mail_item: MailItem,
) -> dict[str, Any]:
    carrier_slug = None
    if mail_item.carrier_id:
        carrier = await session.get(Carrier, mail_item.carrier_id)
        carrier_slug = carrier.slug if carrier else None

    recipient: dict[str, Any] = {}
    if mail_item.recipient_employee_id:
        employee = await session.get(Employee, mail_item.recipient_employee_id)
        if employee is not None:
            department_name = None
            if employee.department_id:
                dept = await session.get(Department, employee.department_id)
                department_name = dept.name if dept else None
            recipient = {
                "employee_id": employee.id,
                "name": employee.name,
                "department": department_name,
            }

    data: dict[str, Any] = {
        "item_no": mail_item.item_no,
        "tracking_no": mail_item.tracking_no,
        "carrier": carrier_slug,
        "recipient": recipient,
        "status": mail_item.status.value,
        "confidential": bool(mail_item.is_confidential),
    }
    if not mail_item.is_confidential:
        data["sender"] = mail_item.sender_org or mail_item.sender_name

    return {
        "event": event,
        "id": f"evt_{uuid7_str()}",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


async def build_outbound_event_payload(
    session,
    *,
    event: str,
    outbound_item: OutboundItem,
) -> dict[str, Any]:
    """M4-01: sibling of `build_event_payload` for `outbound.shipped`
    (03-API-SPEC.md section 3). Shape mirrors the inbound payload as closely
    as the different underlying record allows -- `recipient` here is the
    *applicant* (the employee who requested the shipment), not the mail
    recipient, since outbound_items has no analogous inbound "confidential"
    flag to gate a sender field behind.
    """
    carrier_slug = None
    if outbound_item.carrier_id:
        carrier = await session.get(Carrier, outbound_item.carrier_id)
        carrier_slug = carrier.slug if carrier else None

    applicant: dict[str, Any] = {}
    if outbound_item.applicant_employee_id:
        employee = await session.get(Employee, outbound_item.applicant_employee_id)
        if employee is not None:
            department_name = None
            if employee.department_id:
                dept = await session.get(Department, employee.department_id)
                department_name = dept.name if dept else None
            applicant = {
                "employee_id": employee.id,
                "name": employee.name,
                "department": department_name,
            }

    data: dict[str, Any] = {
        "item_no": outbound_item.item_no,
        "tracking_no": outbound_item.tracking_no,
        "carrier": carrier_slug,
        "applicant": applicant,
        "to_name": outbound_item.to_name,
        "status": outbound_item.status.value,
    }

    return {
        "event": event,
        "id": f"evt_{uuid7_str()}",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
