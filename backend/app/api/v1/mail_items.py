"""收件 (inbound mail_items) endpoints -- 03-API-SPEC.md section 2 "收件":

    POST   /items
    GET    /items
    GET    /items/{id}
    PATCH  /items/{id}          (fields only, status changes go through the
                                  dedicated endpoints below)
    POST   /items/{id}/pickup
    POST   /items/{id}/return
    POST   /items/{id}/forward

Status machine (01-REQUIREMENTS.md section 3):
    received -> notified -> picked_up
    (received|notified|unclaimed) -> returned | forwarded
Any other source status for pickup/return/forward is rejected: an item
already `picked_up` yields ITEM_ALREADY_PICKED (name taken from
03-API-SPEC.md section 4's error-code excerpt); any other terminal state
(`returned`/`forwarded`/`destroyed`) yields ITEM_STATUS_INVALID, which is
this implementation's extension of that excerpt to cover the remaining
terminal states.
"""

from __future__ import annotations

import base64
import binascii
import hmac
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
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
    MailStatus,
    MailType,
    PickupMethod,
    Refrigeration,
    UserRole,
)
from app.models.mail_item import MailItem
from app.models.ocr_job import OcrJob
from app.models.user import User
from app.notify.worker import launch_delivery_for_many
from app.security.csrf import require_csrf
from app.security.file_crypto import (
    InvalidPngError,
    png_dimensions,
    save_encrypted_file,
    validate_png,
)
from app.security.rbac import require_role
from app.security.upload_limits import MAX_SIGNATURE_PNG_BASE64_CHARS, MAX_SIGNATURE_PNG_BYTES
from app.services.audit import record_audit
from app.services.item_no import next_item_no_candidate
from app.services.notify import queue_notifications_for_item
from app.webhooks.events import EVENT_ITEM_PICKED_UP, EVENT_ITEM_RECEIVED, EVENT_ITEM_RETURNED
from app.webhooks.publisher import launch_publish_event

# M1-R1 blocking #4: CSRF-protect every write on this router (require_csrf
# is a no-op for GET/HEAD/OPTIONS, so reads are unaffected).
router = APIRouter(prefix="/items", tags=["mail_items"], dependencies=[Depends(require_csrf)])

READ_ROLES = (UserRole.admin, UserRole.counter, UserRole.viewer)
WRITE_ROLES = (UserRole.admin, UserRole.counter)
CONFIDENTIAL_ROLES = (UserRole.admin, UserRole.counter)

ACTIVE_SOURCE_STATUSES = {MailStatus.received, MailStatus.notified, MailStatus.unclaimed}

_MAX_RETRIES = 5


def serialize_mail_item(
    item: MailItem, *, carrier_name: str | None = None, department_name: str | None = None
) -> dict[str, Any]:
    return {
        "id": item.id,
        "item_no": item.item_no,
        "direction": item.direction,
        "tracking_no": item.tracking_no,
        "carrier_id": item.carrier_id,
        "carrier_name": carrier_name,
        "mail_type": item.mail_type.value,
        "sender_name": item.sender_name,
        "sender_org": item.sender_org,
        "sender_phone": item.sender_phone,
        "recipient_employee_id": item.recipient_employee_id,
        "recipient_name_raw": item.recipient_name_raw,
        "department_id": item.department_id,
        "department_name": department_name,
        "received_at": item.received_at.isoformat(),
        "received_by": item.received_by,
        "status": item.status.value,
        "is_confidential": item.is_confidential,
        "is_cod": item.is_cod,
        "cod_amount": float(item.cod_amount) if item.cod_amount is not None else None,
        "refrigeration": item.refrigeration.value,
        "size_note": item.size_note,
        "note": item.note,
        "notified_at": item.notified_at.isoformat() if item.notified_at else None,
        "remind_count": item.remind_count,
        "picked_up_at": item.picked_up_at.isoformat() if item.picked_up_at else None,
        "picked_up_by_name": item.picked_up_by_name,
        "pickup_method": item.pickup_method.value if item.pickup_method else None,
        "ocr_job_id": item.ocr_job_id,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


async def _item_names(
    session: AsyncSession, item: MailItem
) -> tuple[str | None, str | None]:
    """Resolve carrier/department display names for a single item (detail
    view). The list endpoint joins these in one query instead; this is only
    for the handful of single-item responses."""
    carrier_name = None
    department_name = None
    if item.carrier_id:
        c = await session.get(Carrier, item.carrier_id)
        carrier_name = c.name if c is not None else None
    if item.department_id:
        d = await session.get(Department, item.department_id)
        department_name = d.name if d is not None else None
    return carrier_name, department_name


class MailItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracking_no: str | None = None
    carrier_id: str | None = None
    mail_type: MailType = MailType.parcel
    sender_name: str | None = None
    sender_org: str | None = None
    sender_phone: str | None = None
    recipient_employee_id: str | None = None
    recipient_name_raw: str = Field(min_length=1, max_length=255)
    department_id: str | None = None
    received_at: datetime | None = None
    is_confidential: bool = False
    is_cod: bool = False
    cod_amount: float | None = None
    refrigeration: Refrigeration = Refrigeration.none
    size_note: str | None = None
    note: str | None = None
    # M2-LINK: the OCR-confirm screen (frontend/src/pages/inbound/
    # OcrConfirmPage.vue) posts these two so the photographed label(s) and
    # the OCR job that read them end up linked to the item they created.
    # Both optional and independently validated below -- omitting them keeps
    # the pre-M2-LINK behavior (manual entry, no photos) unchanged.
    ocr_job_id: str | None = None
    attachment_ids: list[str] | None = None


class MailItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracking_no: str | None = None
    carrier_id: str | None = None
    mail_type: MailType | None = None
    sender_name: str | None = None
    sender_org: str | None = None
    sender_phone: str | None = None
    recipient_employee_id: str | None = None
    recipient_name_raw: str | None = Field(default=None, min_length=1, max_length=255)
    department_id: str | None = None
    is_confidential: bool | None = None
    is_cod: bool | None = None
    cod_amount: float | None = None
    refrigeration: Refrigeration | None = None
    size_note: str | None = None
    note: str | None = None


class PickupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: PickupMethod
    picked_up_by_name: str = Field(min_length=1, max_length=255)
    pickup_code: str | None = None
    signature_png_base64: str | None = None


class ReturnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = None


class VoidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Required, and deliberately so. A void is the one transition that says
    # "this record was a mistake"; without a reason the audit trail records
    # that a counter erased something and nothing about why, which is worse
    # than not having the feature. Costs the counter four characters.
    reason: str = Field(min_length=1, max_length=500)


class ForwardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    forward_to: str = Field(min_length=1, max_length=255)
    note: str | None = None


def _bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": code, "message": message})


def _too_large(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=413, detail={"code": code, "message": message})


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404, detail={"code": "NOT_FOUND", "message": "Mail item not found"}
    )


async def _get_or_404(session: AsyncSession, item_id: str) -> MailItem:
    item = await session.get(MailItem, item_id)
    if item is None:
        raise _not_found()
    return item


async def _validate_refs(
    session: AsyncSession,
    *,
    carrier_id: str | None,
    department_id: str | None,
    recipient_employee_id: str | None,
) -> Employee | None:
    if carrier_id is not None:
        carrier = await session.get(Carrier, carrier_id)
        if carrier is None:
            raise _bad_request("CARRIER_NOT_FOUND", "carrier_id does not exist")

    employee: Employee | None = None
    if recipient_employee_id is not None:
        employee = await session.get(Employee, recipient_employee_id)
        if employee is None:
            raise _bad_request("EMPLOYEE_NOT_FOUND", "recipient_employee_id does not exist")

    if department_id is not None:
        dept = await session.get(Department, department_id)
        if dept is None:
            raise _bad_request("DEPARTMENT_NOT_FOUND", "department_id does not exist")

    return employee


async def _validate_attachments_for_bind(
    session: AsyncSession, attachment_ids: list[str] | None
) -> list[Attachment]:
    """Resolves `attachment_ids` (M2-LINK: OCR-confirm -> POST /items) to
    their Attachment rows, enforcing the "pending" invariant documented in
    app/api/v1/uploads.py's module docstring: an attachment created by
    `POST /uploads` is self-owned (`owner_id == attachment.id`) until it is
    confirmed into a real record. Only that pending state may be bound here;
    anything already linked -- to this or any other mail_item/pickup/
    outbound_item -- is rejected rather than silently re-parented, since that
    would let one confirm request steal a photo another job/item already
    claimed.
    """
    attachments: list[Attachment] = []
    for attachment_id in attachment_ids or []:
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
        attachments.append(attachment)
    return attachments


async def _validate_ocr_job_ref(session: AsyncSession, ocr_job_id: str | None) -> None:
    if ocr_job_id is None:
        return
    job = await session.get(OcrJob, ocr_job_id)
    if job is None:
        raise _bad_request("OCR_JOB_NOT_FOUND", "ocr_job_id does not exist")


def _assert_transition_allowed(item: MailItem) -> None:
    if item.status == MailStatus.picked_up:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ITEM_ALREADY_PICKED",
                "message": "This item has already been picked up",
            },
        )
    if item.status not in ACTIVE_SOURCE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ITEM_STATUS_INVALID",
                "message": f"Cannot transition an item in status '{item.status.value}'",
            },
        )


async def _conditional_transition(
    session: AsyncSession, item: MailItem, *, values: dict[str, Any]
) -> bool:
    """Atomically apply `values` (always including a new `status`) only if
    the row is *still* in one of ACTIVE_SOURCE_STATUSES at the moment the
    UPDATE runs.

    M1-R1 blocking #5: the previous pickup/return/forward endpoints did
    read -> `_assert_transition_allowed` -> write as three separate steps
    with no atomicity between them, so two concurrent requests could both
    pass the check against the same pre-write status and both "win" (e.g.
    double pickup). Folding the status check into the UPDATE's WHERE clause
    makes the database the single arbiter: only one concurrent writer can
    ever match `status IN (...)`, and `rowcount` tells the caller whether it
    was this one. `synchronize_session=False` is used because we always
    explicitly `session.refresh(item)` afterwards rather than relying on the
    ORM to reconcile the in-memory object with a Core-level UPDATE.
    """
    result = await session.execute(
        update(MailItem)
        .where(MailItem.id == item.id, MailItem.status.in_(ACTIVE_SOURCE_STATUSES))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


@router.post("", status_code=201)
async def create_item(
    payload: MailItemCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    employee = await _validate_refs(
        session,
        carrier_id=payload.carrier_id,
        department_id=payload.department_id,
        recipient_employee_id=payload.recipient_employee_id,
    )
    pending_attachments = await _validate_attachments_for_bind(session, payload.attachment_ids)
    await _validate_ocr_job_ref(session, payload.ocr_job_id)

    department_id = payload.department_id
    if department_id is None and employee is not None:
        department_id = employee.department_id

    received_at = payload.received_at or datetime.now(timezone.utc)

    item: MailItem | None = None
    for _attempt in range(_MAX_RETRIES):
        item_no = await next_item_no_candidate(session, prefix="IN", when=received_at)
        item = MailItem(
            item_no=item_no,
            direction="inbound",
            tracking_no=payload.tracking_no,
            carrier_id=payload.carrier_id,
            mail_type=payload.mail_type,
            sender_name=payload.sender_name,
            sender_org=payload.sender_org,
            sender_phone=payload.sender_phone,
            recipient_employee_id=payload.recipient_employee_id,
            recipient_name_raw=payload.recipient_name_raw,
            department_id=department_id,
            received_at=received_at,
            received_by=user.id,
            status=MailStatus.received,
            is_confidential=payload.is_confidential,
            is_cod=payload.is_cod,
            cod_amount=payload.cod_amount,
            refrigeration=payload.refrigeration,
            size_note=payload.size_note,
            note=payload.note,
            ocr_job_id=payload.ocr_job_id,
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
        # M1-R1 suggestion: never leak the raw IntegrityError (may include
        # SQL/constraint internals) back to the client.
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "Could not allocate a unique item_no"},
        )

    # M2-LINK: bind the pending (self-owned) attachments the OCR-confirm
    # screen photographed to the item that was just allocated. Rebinding
    # happens only now (not in `_validate_attachments_for_bind`) because it
    # needs `item.id`, which only exists after the flush above.
    for attachment in pending_attachments:
        attachment.owner_type = AttachmentOwnerType.mail_item
        attachment.owner_id = item.id
        attachment.kind = AttachmentKind.label_photo
    if pending_attachments:
        await session.flush()

    created_notifications = await queue_notifications_for_item(
        session, mail_item_id=item.id, employee_id=item.recipient_employee_id
    )

    await record_audit(
        session,
        request=request,
        actor=user,
        action="mail_item.create",
        target_type="mail_item",
        target_id=item.id,
        diff={
            "after": serialize_mail_item(item),
            "attachment_ids": [a.id for a in pending_attachments] or None,
        },
    )
    await session.commit()
    await session.refresh(item)

    # M3-01: background delivery (retry/backoff/dead-letter,
    # app/notify/worker.py) + the external item.received webhook
    # (03-API-SPEC.md section 3) both only start *after* the row/commit is
    # durable -- same "commit then launch background task" shape as
    # app/api/v1/ocr_jobs.py.
    launch_delivery_for_many([n.id for n in created_notifications])
    await launch_publish_event(session, event=EVENT_ITEM_RECEIVED, mail_item_id=item.id)

    carrier_name, department_name = await _item_names(session, item)
    return ok(
        serialize_mail_item(
            item, carrier_name=carrier_name, department_name=department_name
        )
    )


@router.get("")
async def list_items(
    pagination: tuple[int, int] = Depends(pagination_params),
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
    page, size = pagination
    stmt = (
        select(MailItem, Carrier.name, Department.name)
        .outerjoin(Carrier, MailItem.carrier_id == Carrier.id)
        .outerjoin(Department, MailItem.department_id == Department.id)
    )
    count_stmt = select(func.count()).select_from(MailItem)

    conditions = []
    if q:
        like = f"%{q}%"
        conditions.append(
            or_(
                MailItem.item_no.ilike(like),
                MailItem.tracking_no.ilike(like),
                MailItem.sender_name.ilike(like),
                MailItem.recipient_name_raw.ilike(like),
            )
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

    # Viewer never sees confidential mail items, regardless of the
    # `confidential` filter -- item detail is admin/counter-only per
    # 01-REQUIREMENTS.md section 4, and this keeps the list consistent
    # with that (a viewer could otherwise infer confidential contents from
    # list metadata like sender/tracking even without opening the detail).
    if user.role == UserRole.viewer:
        conditions.append(MailItem.is_confidential.is_(False))
    elif confidential is not None:
        conditions.append(MailItem.is_confidential == confidential)

    for cond in conditions:
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(MailItem.received_at.desc()).offset((page - 1) * size).limit(size)
    rows = (await session.execute(stmt)).all()

    return paginated(
        [
            serialize_mail_item(item, carrier_name=cname, department_name=dname)
            for item, cname, dname in rows
        ],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{item_id}")
async def get_item(
    item_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*READ_ROLES)),
):
    item = await _get_or_404(session, item_id)

    if item.is_confidential:
        if user.role not in CONFIDENTIAL_ROLES:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "FORBIDDEN",
                    "message": "Confidential items may only be viewed by admin/counter",
                },
            )
        await record_audit(
            session,
            request=request,
            actor=user,
            action="mail_item.view_confidential",
            target_type="mail_item",
            target_id=item.id,
        )
        await session.commit()

    carrier_name, department_name = await _item_names(session, item)
    return ok(
        serialize_mail_item(item, carrier_name=carrier_name, department_name=department_name)
    )


@router.patch("/{item_id}")
async def update_item(
    item_id: str,
    payload: MailItemUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    item = await _get_or_404(session, item_id)
    before = serialize_mail_item(item)

    updates = payload.model_dump(exclude_unset=True)
    await _validate_refs(
        session,
        carrier_id=updates.get("carrier_id"),
        department_id=updates.get("department_id"),
        recipient_employee_id=updates.get("recipient_employee_id"),
    )

    for field, value in updates.items():
        setattr(item, field, value)

    await session.flush()
    after = serialize_mail_item(item)

    await record_audit(
        session,
        request=request,
        actor=user,
        action="mail_item.update",
        target_type="mail_item",
        target_id=item.id,
        diff={"before": before, "after": after},
    )
    await session.commit()
    await session.refresh(item)
    carrier_name, department_name = await _item_names(session, item)
    return ok(
        serialize_mail_item(
            item, carrier_name=carrier_name, department_name=department_name
        )
    )


@router.post("/{item_id}/pickup")
async def pickup_item(
    item_id: str,
    payload: PickupRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    item = await _get_or_404(session, item_id)
    _assert_transition_allowed(item)

    if payload.method not in (PickupMethod.pickup_code, PickupMethod.signature):
        raise _bad_request(
            "PICKUP_METHOD_UNSUPPORTED", f"Unsupported pickup method '{payload.method.value}'"
        )

    before = serialize_mail_item(item)
    attachment_id: str | None = None

    if payload.method == PickupMethod.pickup_code:
        if not payload.pickup_code:
            raise _bad_request("PICKUP_CODE_INVALID", "pickup_code is required for this method")
        employee = (
            await session.get(Employee, item.recipient_employee_id)
            if item.recipient_employee_id
            else None
        )
        # M1-R1 suggestion: constant-time comparison (hmac.compare_digest)
        # rather than `!=`, consistent with app/api/v1/pickup.py.
        if (
            employee is None
            or not employee.pickup_code
            or not hmac.compare_digest(employee.pickup_code, payload.pickup_code)
        ):
            raise HTTPException(
                status_code=422,
                detail={"code": "PICKUP_CODE_INVALID", "message": "pickup_code does not match"},
            )
    else:  # signature
        if not payload.signature_png_base64:
            raise _bad_request(
                "UPLOAD_BAD_TYPE", "signature_png_base64 is required for this method"
            )
        # M1-R1 blocking #1: reject an oversized payload by its encoded
        # length *before* spending time base64-decoding it.
        if len(payload.signature_png_base64) > MAX_SIGNATURE_PNG_BASE64_CHARS:
            raise _too_large(
                "UPLOAD_TOO_LARGE",
                f"signature_png_base64 exceeds the {MAX_SIGNATURE_PNG_BYTES} byte limit",
            )
        try:
            png_bytes = base64.b64decode(payload.signature_png_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise _bad_request(
                "UPLOAD_BAD_TYPE", "signature_png_base64 is not valid base64"
            ) from exc
        # Authoritative check on the decoded size (the base64-length check
        # above is a cheap pre-filter, not a substitute for this).
        if len(png_bytes) > MAX_SIGNATURE_PNG_BYTES:
            raise _too_large(
                "UPLOAD_TOO_LARGE",
                f"signature_png_base64 exceeds the {MAX_SIGNATURE_PNG_BYTES} byte limit",
            )
        try:
            validate_png(png_bytes)
        except InvalidPngError as exc:
            raise _bad_request("UPLOAD_BAD_TYPE", str(exc)) from exc

        stored = save_encrypted_file(
            png_bytes, subdir=f"pickup_signatures/{item.id}", extension="png"
        )
        width, height = png_dimensions(png_bytes)
        attachment = Attachment(
            owner_type=AttachmentOwnerType.pickup,
            owner_id=item.id,
            kind=AttachmentKind.pickup_signature,
            file_path=stored["file_path"],
            sha256=stored["sha256"],
            mime="image/png",
            size_bytes=stored["size_bytes"],
            width=width,
            height=height,
        )
        session.add(attachment)
        await session.flush()
        attachment_id = attachment.id

    # M1-R1 blocking #5: atomic conditional UPDATE instead of mutating
    # `item` in place -- see `_conditional_transition` docstring. If we lose
    # the race, re-fetch and let `_assert_transition_allowed` report the
    # precise reason (almost always ITEM_ALREADY_PICKED).
    won = await _conditional_transition(
        session,
        item,
        values={
            "status": MailStatus.picked_up,
            "picked_up_at": datetime.now(timezone.utc),
            "picked_up_by_name": payload.picked_up_by_name,
            "pickup_method": payload.method,
        },
    )
    if not won:
        await session.refresh(item)
        _assert_transition_allowed(item)

    await session.refresh(item)
    after = serialize_mail_item(item)

    await record_audit(
        session,
        request=request,
        actor=user,
        action="mail_item.pickup",
        target_type="mail_item",
        target_id=item.id,
        diff={
            "before": before,
            "after": after,
            "method": payload.method.value,
            "attachment_id": attachment_id,
        },
    )
    await session.commit()
    await session.refresh(item)
    await launch_publish_event(session, event=EVENT_ITEM_PICKED_UP, mail_item_id=item.id)
    carrier_name, department_name = await _item_names(session, item)
    return ok(
        serialize_mail_item(
            item, carrier_name=carrier_name, department_name=department_name
        )
    )


@router.post("/{item_id}/void")
async def void_item(
    item_id: str,
    payload: VoidRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    """Mark a registration as a mistake (雙重登記、拍錯照、按錯送出).

    Why this exists as its own status rather than a delete: the counter *will*
    mis-register things -- it's a person with a phone at a busy desk -- and
    until now the only escape was to fake a `returned`, which told the reports
    a parcel went back to its sender when no parcel ever existed. So the counts
    lied, and the audit trail recorded a return that never happened.

    Why not a hard delete: `audit_logs` is append-only on purpose. An item that
    can vanish takes its own history with it, and "who deleted this and why" is
    exactly the question an audit exists to answer. The row stays, carries its
    reason, and is excluded from reports and every pickup path instead.

    Only reachable from ACTIVE_SOURCE_STATUSES (via `_assert_transition_allowed`),
    so a picked-up item can't be voided -- that signature records something that
    really happened, and unpicking it is not a mistake-correction, it's erasing
    evidence.
    """
    item = await _get_or_404(session, item_id)
    _assert_transition_allowed(item)

    before = serialize_mail_item(item)
    void_note = f"[voided] {payload.reason}"
    new_note = f"{item.note}\n{void_note}" if item.note else void_note

    won = await _conditional_transition(
        session, item, values={"status": MailStatus.voided, "note": new_note}
    )
    if not won:
        await session.refresh(item)
        _assert_transition_allowed(item)

    await session.refresh(item)
    after = serialize_mail_item(item)
    await record_audit(
        session,
        request=request,
        actor=user,
        action="mail_item.void",
        target_type="mail_item",
        target_id=item.id,
        diff={"before": before, "after": after, "reason": payload.reason},
    )
    await session.commit()
    await session.refresh(item)
    carrier_name, department_name = await _item_names(session, item)
    return ok(
        serialize_mail_item(
            item, carrier_name=carrier_name, department_name=department_name
        )
    )


@router.post("/{item_id}/return")
async def return_item(
    item_id: str,
    payload: ReturnRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    item = await _get_or_404(session, item_id)
    _assert_transition_allowed(item)

    before = serialize_mail_item(item)
    new_note = item.note
    if payload.note:
        return_note = f"[returned] {payload.note}"
        new_note = f"{item.note}\n{return_note}" if item.note else return_note

    # M1-R1 blocking #5: atomic conditional UPDATE (see `_conditional_transition`).
    won = await _conditional_transition(
        session, item, values={"status": MailStatus.returned, "note": new_note}
    )
    if not won:
        await session.refresh(item)
        _assert_transition_allowed(item)

    await session.refresh(item)
    after = serialize_mail_item(item)

    await record_audit(
        session,
        request=request,
        actor=user,
        action="mail_item.return",
        target_type="mail_item",
        target_id=item.id,
        diff={"before": before, "after": after},
    )
    await session.commit()
    await session.refresh(item)
    await launch_publish_event(session, event=EVENT_ITEM_RETURNED, mail_item_id=item.id)
    carrier_name, department_name = await _item_names(session, item)
    return ok(
        serialize_mail_item(
            item, carrier_name=carrier_name, department_name=department_name
        )
    )


@router.post("/{item_id}/forward")
async def forward_item(
    item_id: str,
    payload: ForwardRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    item = await _get_or_404(session, item_id)
    _assert_transition_allowed(item)

    before = serialize_mail_item(item)
    forward_note = f"[forwarded] to={payload.forward_to}"
    if payload.note:
        forward_note += f"; note={payload.note}"
    new_note = f"{item.note}\n{forward_note}" if item.note else forward_note

    # M1-R1 blocking #5: atomic conditional UPDATE (see `_conditional_transition`).
    won = await _conditional_transition(
        session, item, values={"status": MailStatus.forwarded, "note": new_note}
    )
    if not won:
        await session.refresh(item)
        _assert_transition_allowed(item)

    await session.refresh(item)
    after = serialize_mail_item(item)

    await record_audit(
        session,
        request=request,
        actor=user,
        action="mail_item.forward",
        target_type="mail_item",
        target_id=item.id,
        diff={"before": before, "after": after, "forward_to": payload.forward_to},
    )
    await session.commit()
    await session.refresh(item)
    carrier_name, department_name = await _item_names(session, item)
    return ok(
        serialize_mail_item(
            item, carrier_name=carrier_name, department_name=department_name
        )
    )
