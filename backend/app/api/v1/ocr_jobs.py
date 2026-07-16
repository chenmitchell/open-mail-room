"""OCR job lifecycle (03-API-SPEC.md section 2 "照片與 OCR"):

    POST /ocr/jobs              {attachment_ids: [...], mail_type?}
                                 -> one job covering all given attachments
                                    (04-AI-OCR.md section 3: "同一件多張照片
                                    ...ocr_jobs 因此允許一個 job 綁多個
                                    attachment"), run in the background.
    GET  /ocr/jobs/{id}          poll job status.
    GET  /ocr/jobs/{id}/draft    pre-filled fields + employee-match
                                  candidates + barcode fields, for the
                                  counter-confirmation screen.

Confidential-item gating (04-AI-OCR.md section 5: "機密件...可設定禁用 AI
OCR,僅手動"): a mail item's `is_confidential` flag normally only exists
*after* `POST /items`, which happens *after* OCR confirmation -- so this
endpoint accepts an explicit `is_confidential` flag on the request (the
counter marks a piece confidential *before* photographing it) and also
independently checks any attachment that already belongs to a confirmed
confidential `mail_items` row (re-run-OCR scenario). Either one blocks job
creation with `OCR_CONFIDENTIAL_DISABLED`.

`GET /ocr/jobs/{id}/draft` gets the same restriction mirrored from
`GET /uploads/{id}` (app/api/v1/uploads.py, M2-R1 contract gap #5): every
attachment an OCR job covers is still "pending" (self-owned, not yet
confirmed into a `mail_items` row) at draft-review time -- the draft *is*
the pre-confirmation screen -- so `app.services.confidential.resolve_is_confidential`
treats it the same as confidential (restricted to admin/counter) until
confirmed. A re-run-OCR job on an attachment that's already linked to a
confirmed confidential item is restricted the same way.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok
from app.db import get_session
from app.models.attachment import Attachment
from app.models.employee import Employee
from app.models.enums import AttachmentOwnerType, EmployeeStatus, MailType, OcrStatus, UserRole
from app.models.mail_item import MailItem
from app.models.ocr_job import OcrJob
from app.models.user import User
from app.ocr.pipeline import run_ocr_job
from app.security.csrf import require_csrf
from app.security.rbac import require_role
from app.services.audit import record_audit
from app.services.confidential import resolve_is_confidential
from app.services.matching import CANDIDATE_THRESHOLD, match_departments, match_employees

router = APIRouter(prefix="/ocr/jobs", tags=["ocr_jobs"], dependencies=[Depends(require_csrf)])

WRITE_ROLES = (UserRole.admin, UserRole.counter)
READ_ROLES = (UserRole.admin, UserRole.counter, UserRole.viewer)
CONFIDENTIAL_ROLES = (UserRole.admin, UserRole.counter)

MAX_ATTACHMENTS_PER_JOB = 30

# Keeps a strong reference to in-flight background tasks so they are not
# garbage-collected mid-run (a bare `asyncio.create_task(...)` result with no
# other referent is only weakly protected by the event loop).
_background_tasks: set[asyncio.Task] = set()


def _launch_background(job_id: str, *, mail_type: MailType | None) -> None:
    task = asyncio.create_task(run_ocr_job(job_id, mail_type=mail_type))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class OcrJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_ids: list[str] = Field(min_length=1, max_length=MAX_ATTACHMENTS_PER_JOB)
    mail_type: MailType | None = None
    is_confidential: bool = False
    # attachment_id -> barcode string already decoded client-side (zxing) --
    # 04-AI-OCR.md section 3: "barcode_results 由前端掃到後隨 upload 附上".
    barcode_hints: dict[str, str] | None = None


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404, detail={"code": "NOT_FOUND", "message": "OCR job not found"}
    )


def _confidential_disabled() -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": "OCR_CONFIDENTIAL_DISABLED",
            "message": "AI OCR is disabled for confidential items; enter fields manually",
        },
    )


def serialize_job(job: OcrJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "attachment_ids": job.attachment_ids,
        "provider": job.provider,
        "model": job.model,
        "status": job.status.value,
        "confidence": job.confidence,
        "prompt_version": job.prompt_version,
        "tokens_in": job.tokens_in,
        "tokens_out": job.tokens_out,
        "cost_estimate": job.cost_estimate,
        "error": job.error,
        "retries": job.retries,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


@router.post("", status_code=201)
async def create_ocr_job(
    payload: OcrJobCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    if payload.is_confidential:
        raise _confidential_disabled()

    attachments: list[Attachment] = []
    for attachment_id in payload.attachment_ids:
        attachment = await session.get(Attachment, attachment_id)
        if attachment is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "ATTACHMENT_NOT_FOUND",
                    "message": f"attachment_id '{attachment_id}' does not exist",
                },
            )
        attachments.append(attachment)

        if attachment.owner_type in (
            AttachmentOwnerType.mail_item,
            AttachmentOwnerType.pickup,
        ) and attachment.owner_id != attachment.id:
            linked_item = await session.get(MailItem, attachment.owner_id)
            if linked_item is not None and linked_item.is_confidential:
                raise _confidential_disabled()

    job = OcrJob(
        attachment_ids=list(payload.attachment_ids),
        status=OcrStatus.queued,
        barcode_results=payload.barcode_hints or None,
    )
    session.add(job)
    await session.flush()

    await record_audit(
        session,
        request=request,
        actor=user,
        action="ocr_job.create",
        target_type="ocr_job",
        target_id=job.id,
        diff={"attachment_ids": job.attachment_ids, "mail_type": payload.mail_type},
    )
    await session.commit()
    await session.refresh(job)

    _launch_background(job.id, mail_type=payload.mail_type)

    return ok(serialize_job(job))


@router.get("/{job_id}")
async def get_ocr_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*READ_ROLES)),
):
    job = await session.get(OcrJob, job_id)
    if job is None:
        raise _not_found()
    return ok(serialize_job(job))


async def _job_confidentiality(session: AsyncSession, job: OcrJob) -> tuple[bool, bool]:
    """Mirrors uploads.py's `GET /uploads/{id}` gating (M2-R1 contract gap
    #5). Returns `(restricted, genuinely_confidential)`:
    - `restricted` is True if *any* attachment this job covers is still
      pending (unconfirmed) or is linked to a confirmed confidential
      mail_item -- callers must block non-admin/counter roles.
    - `genuinely_confidential` is True only for the confirmed-confidential
      case (not merely "pending"), for the audit-log write below, matching
      uploads.py's own `if is_confidential:` condition.
    """
    restricted = False
    genuinely_confidential = False
    for attachment_id in job.attachment_ids:
        attachment = await session.get(Attachment, attachment_id)
        if attachment is None:
            continue
        is_confidential = await resolve_is_confidential(session, attachment)
        if is_confidential is None:
            restricted = True
        elif is_confidential:
            restricted = True
            genuinely_confidential = True
    return restricted, genuinely_confidential


@router.get("/{job_id}/draft")
async def get_ocr_job_draft(
    job_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*READ_ROLES)),
):
    job = await session.get(OcrJob, job_id)
    if job is None:
        raise _not_found()

    restricted, genuinely_confidential = await _job_confidentiality(session, job)
    if restricted and user.role not in CONFIDENTIAL_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FORBIDDEN",
                "message": "This OCR draft may only be viewed by admin/counter",
            },
        )
    if genuinely_confidential:
        await record_audit(
            session,
            request=request,
            actor=user,
            action="ocr_job.view_confidential_draft",
            target_type="ocr_job",
            target_id=job.id,
        )
        await session.commit()

    result = job.result_json or {}
    draft = {
        "tracking_no": result.get("tracking_no"),
        "carrier_id": result.get("carrier_id"),
        "carrier_guess": result.get("carrier_guess"),
        "sender_name": result.get("sender_name"),
        "sender_org": result.get("sender_org"),
        "sender_phone": result.get("sender_phone"),
        # NOTE: key MUST be "recipient_name" to match the frontend's
        # OcrDraftFields type + createFormFromOcrDraft (was "recipient_name_raw",
        # which the frontend never read -> the recipient field silently stayed
        # empty on every OCR confirm, regardless of what the AI extracted).
        "recipient_name": result.get("recipient_name"),
        "recipient_dept_hint": result.get("recipient_dept_hint"),
        "is_handwritten": result.get("is_handwritten"),
        "confidence": job.confidence,
        "warnings": result.get("warnings", []),
    }

    employee_candidates: list[dict] = []
    recipient_name = result.get("recipient_name")
    if job.status == OcrStatus.succeeded and recipient_name:
        employee_candidates = await match_employees(session, recipient_name, limit=5)

    # 部門件 (A): if the AI read a company/unit (recipient_dept_hint) or the
    # recipient itself looks like a department, offer department candidates so
    # the counter can route the item to that department's contact person
    # (each candidate carries manager_employee_id + manager_name).
    department_candidates: list[dict] = []
    dept_query = result.get("recipient_dept_hint") or result.get("recipient_name")
    if job.status == OcrStatus.succeeded and dept_query:
        for d in await match_departments(
            session, dept_query, limit=5, min_score=CANDIDATE_THRESHOLD
        ):
            manager_name = None
            manager_id = d.get("manager_employee_id")
            if manager_id:
                mgr = await session.get(Employee, manager_id)
                # An inactive or deleted contact can't receive the item, so
                # treat it as "no contact set" -> the UI disables that
                # department (review SHOULD-FIX #4).
                if mgr is None or mgr.status != EmployeeStatus.active:
                    manager_id = None
                else:
                    manager_name = mgr.name
            department_candidates.append(
                {**d, "manager_employee_id": manager_id, "manager_name": manager_name}
            )

    return ok(
        {
            "job_id": job.id,
            "status": job.status.value,
            "error": job.error,
            "draft": draft,
            "employee_candidates": employee_candidates,
            "department_candidates": department_candidates,
            "barcode_results": job.barcode_results or {},
        }
    )
