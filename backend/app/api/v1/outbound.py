"""交寄 (outbound_items) endpoints -- 03-API-SPEC.md section 2 "交寄":

    POST   /outbound
    GET    /outbound
    GET    /outbound/{id}
    PATCH  /outbound/{id}          (fields only; the status transition goes
                                     through the dedicated endpoint below)
    POST   /outbound/{id}/shipped

01-REQUIREMENTS.md section 2.2: "員工或櫃台建立交寄單" -- create is open to
`employee` in addition to admin/counter, but an `employee` caller can only
ever create a request for *themselves* (their `applicant_employee_id` is
always derived server-side from `employees.user_id`, never taken from the
request body) since there is no counter-staff judgment call happening on
their side of that request. Confirming shipment ("交寄時拍託運單照片 ->
OCR 抽單號回填 -> 狀態「已交寄」") is a physical, at-the-counter action, so
`PATCH` and `POST .../shipped` are admin/counter only, same split as
app/api/v1/mail_items.py's WRITE_ROLES vs the employee-facing app/api/v1/
me_items.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok, paginated
from app.api.v1._common import pagination_params
from app.db import get_session
from app.models.attachment import Attachment
from app.models.carrier import Carrier
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import (
    AttachmentKind,
    AttachmentOwnerType,
    OutboundPayment,
    OutboundStatus,
    UserRole,
)
from app.models.outbound_item import OutboundItem
from app.models.user import User
from app.notify.worker import launch_delivery_for_many
from app.security.csrf import require_csrf
from app.security.rbac import require_role
from app.services.audit import record_audit
from app.services.item_no import next_item_no_candidate
from app.services.notify import queue_notifications_for_outbound
from app.webhooks.events import EVENT_OUTBOUND_SHIPPED
from app.webhooks.publisher import launch_publish_outbound_event

router = APIRouter(prefix="/outbound", tags=["outbound"], dependencies=[Depends(require_csrf)])

READ_ROLES = (UserRole.admin, UserRole.counter, UserRole.viewer)
CREATE_ROLES = (UserRole.admin, UserRole.counter, UserRole.employee)
WRITE_ROLES = (UserRole.admin, UserRole.counter)

_MAX_RETRIES = 5


def serialize_outbound_item(
    item: OutboundItem,
    *,
    applicant_name: str | None = None,
    department_name: str | None = None,
    carrier_name: str | None = None,
) -> dict[str, Any]:
    """The *_name fields are display-only denormalizations the outbound list
    renders directly. They are passed in rather than lazy-loaded because the
    list endpoint resolves all three in its own join -- serializing N items
    must not mean 3N extra queries. Callers that don't have them (audit diffs,
    for instance, which record IDs) simply omit them and get nulls."""
    return {
        "id": item.id,
        "item_no": item.item_no,
        "applicant_employee_id": item.applicant_employee_id,
        "applicant_name": applicant_name,
        "department_id": item.department_id,
        "department_name": department_name,
        "to_name": item.to_name,
        "to_org": item.to_org,
        "to_address": item.to_address,
        "to_phone": item.to_phone,
        "carrier_id": item.carrier_id,
        "carrier_name": carrier_name,
        "tracking_no": item.tracking_no,
        "shipped_at": item.shipped_at.isoformat() if item.shipped_at else None,
        "cost": float(item.cost) if item.cost is not None else None,
        "payment": item.payment.value if item.payment else None,
        "status": item.status.value,
        "note": item.note,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


async def _item_names(
    session: AsyncSession, item: OutboundItem
) -> dict[str, str | None]:
    """Resolve the three display names for a single-item response. The list
    endpoint joins them in one query instead; this only ever runs for the
    handful of responses that carry one item."""
    names: dict[str, str | None] = {
        "applicant_name": None,
        "department_name": None,
        "carrier_name": None,
    }
    if item.applicant_employee_id:
        emp = await session.get(Employee, item.applicant_employee_id)
        names["applicant_name"] = emp.name if emp is not None else None
    if item.department_id:
        dept = await session.get(Department, item.department_id)
        names["department_name"] = dept.name if dept is not None else None
    if item.carrier_id:
        carrier = await session.get(Carrier, item.carrier_id)
        names["carrier_name"] = carrier.name if carrier is not None else None
    return names


class OutboundItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicant_employee_id: str | None = None
    department_id: str | None = None
    to_name: str | None = None
    to_org: str | None = None
    to_address: str | None = None
    to_phone: str | None = None
    carrier_id: str | None = None
    tracking_no: str | None = None
    cost: float | None = None
    payment: OutboundPayment | None = None
    note: str | None = None


class OutboundItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicant_employee_id: str | None = None
    department_id: str | None = None
    to_name: str | None = None
    to_org: str | None = None
    to_address: str | None = None
    to_phone: str | None = None
    carrier_id: str | None = None
    tracking_no: str | None = None
    cost: float | None = None
    payment: OutboundPayment | None = None
    note: str | None = None


class OutboundShippedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracking_no: str | None = None
    attachment_id: str | None = None


def _bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": code, "message": message})


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404, detail={"code": "NOT_FOUND", "message": "Outbound item not found"}
    )


def _forbidden(message: str = "Not permitted for this outbound item") -> HTTPException:
    return HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": message})


async def _get_or_404(session: AsyncSession, item_id: str) -> OutboundItem:
    item = await session.get(OutboundItem, item_id)
    if item is None:
        raise _not_found()
    return item


async def _current_employee(session: AsyncSession, user: User) -> Employee | None:
    result = await session.execute(select(Employee).where(Employee.user_id == user.id))
    return result.scalar_one_or_none()


async def _validate_refs(
    session: AsyncSession,
    *,
    applicant_employee_id: str | None,
    department_id: str | None,
    carrier_id: str | None,
) -> None:
    if applicant_employee_id is not None:
        employee = await session.get(Employee, applicant_employee_id)
        if employee is None:
            raise _bad_request(
                "EMPLOYEE_NOT_FOUND", "applicant_employee_id does not exist"
            )
    if department_id is not None:
        dept = await session.get(Department, department_id)
        if dept is None:
            raise _bad_request("DEPARTMENT_NOT_FOUND", "department_id does not exist")
    if carrier_id is not None:
        carrier = await session.get(Carrier, carrier_id)
        if carrier is None:
            raise _bad_request("CARRIER_NOT_FOUND", "carrier_id does not exist")


async def _validate_attachment_for_bind(
    session: AsyncSession, attachment_id: str | None
) -> Attachment | None:
    """Same "pending -> confirm" invariant as
    app/api/v1/mail_items.py's `_validate_attachments_for_bind`: an
    attachment created by `POST /uploads` is self-owned
    (`owner_id == attachment.id`) until it is bound into a real record.
    """
    if attachment_id is None:
        return None
    attachment = await session.get(Attachment, attachment_id)
    if attachment is None:
        raise _bad_request(
            "ATTACHMENT_NOT_FOUND", f"attachment_id '{attachment_id}' does not exist"
        )
    if attachment.owner_id != attachment.id:
        raise _bad_request(
            "ATTACHMENT_ALREADY_LINKED",
            f"attachment_id '{attachment_id}' is already linked to another record",
        )
    return attachment


@router.post("", status_code=201)
async def create_outbound_item(
    payload: OutboundItemCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*CREATE_ROLES)),
):
    applicant_employee_id = payload.applicant_employee_id
    department_id = payload.department_id

    if user.role == UserRole.employee:
        # An employee can only ever file a request for themselves -- never
        # trust a client-supplied applicant_employee_id for this role.
        self_employee = await _current_employee(session, user)
        if self_employee is None:
            raise _bad_request(
                "EMPLOYEE_NOT_LINKED",
                "Your account is not linked to an employee directory record",
            )
        applicant_employee_id = self_employee.id
        if department_id is None:
            department_id = self_employee.department_id

    await _validate_refs(
        session,
        applicant_employee_id=applicant_employee_id,
        department_id=department_id,
        carrier_id=payload.carrier_id,
    )

    if department_id is None and applicant_employee_id is not None:
        employee = await session.get(Employee, applicant_employee_id)
        if employee is not None:
            department_id = employee.department_id

    item: OutboundItem | None = None
    now = datetime.now(timezone.utc)
    for _attempt in range(_MAX_RETRIES):
        item_no = await next_item_no_candidate(session, prefix="OUT", when=now)
        item = OutboundItem(
            item_no=item_no,
            applicant_employee_id=applicant_employee_id,
            department_id=department_id,
            to_name=payload.to_name,
            to_org=payload.to_org,
            to_address=payload.to_address,
            to_phone=payload.to_phone,
            carrier_id=payload.carrier_id,
            tracking_no=payload.tracking_no,
            cost=payload.cost,
            payment=payload.payment,
            status=OutboundStatus.pending,
            note=payload.note,
        )
        session.add(item)
        try:
            await session.flush()
            break
        except IntegrityError:
            await session.rollback()
            item = None
            continue

    if item is None:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "Could not allocate a unique item_no"},
        )

    await record_audit(
        session,
        request=request,
        actor=user,
        action="outbound_item.create",
        target_type="outbound_item",
        target_id=item.id,
        diff={"after": serialize_outbound_item(item)},
    )
    await session.commit()
    await session.refresh(item)
    return ok(serialize_outbound_item(item, **await _item_names(session, item)))


@router.get("")
async def list_outbound_items(
    pagination: tuple[int, int] = Depends(pagination_params),
    q: str | None = None,
    status: OutboundStatus | None = None,
    carrier_id: str | None = None,
    department_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*READ_ROLES, UserRole.employee)),
):
    page, size = pagination
    stmt = (
        select(OutboundItem, Employee.name, Department.name, Carrier.name)
        .outerjoin(Employee, OutboundItem.applicant_employee_id == Employee.id)
        .outerjoin(Department, OutboundItem.department_id == Department.id)
        .outerjoin(Carrier, OutboundItem.carrier_id == Carrier.id)
    )
    count_stmt = select(func.count()).select_from(OutboundItem)

    conditions = []
    if user.role == UserRole.employee:
        # RC-FIX #4: an `employee` caller is allowed to list outbound items
        # (01-REQUIREMENTS.md "員工或櫃台建立交寄單" implies they also need
        # to see their own requests), but only their own -- same self-check
        # `get_outbound_item` already applies per-item, enforced here at the
        # query level instead of filtering the response afterward.
        self_employee = await _current_employee(session, user)
        if self_employee is None:
            return paginated([], total=0, page=page, size=size)
        conditions.append(OutboundItem.applicant_employee_id == self_employee.id)
    if q:
        like = f"%{q}%"
        conditions.append(
            or_(
                OutboundItem.item_no.ilike(like),
                OutboundItem.tracking_no.ilike(like),
                OutboundItem.to_name.ilike(like),
            )
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
        count_stmt = count_stmt.where(cond)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(OutboundItem.created_at.desc()).offset((page - 1) * size).limit(size)
    rows = (await session.execute(stmt)).all()

    return paginated(
        [
            serialize_outbound_item(
                item,
                applicant_name=applicant_name,
                department_name=department_name,
                carrier_name=carrier_name,
            )
            for item, applicant_name, department_name, carrier_name in rows
        ],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{item_id}")
async def get_outbound_item(
    item_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*READ_ROLES, UserRole.employee)),
):
    item = await _get_or_404(session, item_id)
    if user.role == UserRole.employee:
        self_employee = await _current_employee(session, user)
        if self_employee is None or item.applicant_employee_id != self_employee.id:
            raise _forbidden()
    return ok(serialize_outbound_item(item, **await _item_names(session, item)))


@router.patch("/{item_id}")
async def update_outbound_item(
    item_id: str,
    payload: OutboundItemUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    item = await _get_or_404(session, item_id)
    before = serialize_outbound_item(item)

    updates = payload.model_dump(exclude_unset=True)
    await _validate_refs(
        session,
        applicant_employee_id=updates.get("applicant_employee_id"),
        department_id=updates.get("department_id"),
        carrier_id=updates.get("carrier_id"),
    )

    for field, value in updates.items():
        setattr(item, field, value)

    await session.flush()
    after = serialize_outbound_item(item)

    await record_audit(
        session,
        request=request,
        actor=user,
        action="outbound_item.update",
        target_type="outbound_item",
        target_id=item.id,
        diff={"before": before, "after": after},
    )
    await session.commit()
    await session.refresh(item)
    return ok(serialize_outbound_item(item, **await _item_names(session, item)))


@router.post("/{item_id}/shipped")
async def mark_outbound_shipped(
    item_id: str,
    payload: OutboundShippedRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    item = await _get_or_404(session, item_id)
    if item.status != OutboundStatus.pending:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OUTBOUND_STATUS_INVALID",
                "message": (
                    f"Cannot mark an outbound item in status '{item.status.value}' as shipped"
                ),
            },
        )

    attachment = await _validate_attachment_for_bind(session, payload.attachment_id)
    before = serialize_outbound_item(item)
    now = datetime.now(timezone.utc)

    # Atomic conditional UPDATE (mirrors app/api/v1/mail_items.py's
    # `_conditional_transition`): only succeeds if the row is *still*
    # `pending` at the moment the UPDATE runs, so two concurrent "mark
    # shipped" calls for the same item can't both win.
    values: dict[str, Any] = {"status": OutboundStatus.shipped, "shipped_at": now}
    if payload.tracking_no:
        values["tracking_no"] = payload.tracking_no
    result = await session.execute(
        update(OutboundItem)
        .where(OutboundItem.id == item.id, OutboundItem.status == OutboundStatus.pending)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await session.refresh(item)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OUTBOUND_STATUS_INVALID",
                "message": (
                    f"Cannot mark an outbound item in status '{item.status.value}' as shipped"
                ),
            },
        )

    if attachment is not None:
        attachment.owner_type = AttachmentOwnerType.outbound_item
        attachment.owner_id = item.id
        attachment.kind = AttachmentKind.label_photo

    await session.flush()
    await session.refresh(item)
    after = serialize_outbound_item(item)

    await record_audit(
        session,
        request=request,
        actor=user,
        action="outbound_item.shipped",
        target_type="outbound_item",
        target_id=item.id,
        diff={
            "before": before,
            "after": after,
            "attachment_id": attachment.id if attachment else None,
        },
    )
    await session.commit()
    await session.refresh(item)

    created_notifications = await queue_notifications_for_outbound(
        session, outbound_item_id=item.id, employee_id=item.applicant_employee_id
    )
    await session.commit()
    launch_delivery_for_many([n.id for n in created_notifications])
    await launch_publish_outbound_event(
        session, event=EVENT_OUTBOUND_SHIPPED, outbound_item_id=item.id
    )

    return ok(serialize_outbound_item(item, **await _item_names(session, item)))
