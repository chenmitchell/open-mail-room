"""Photo intake for OCR (03-API-SPEC.md section 2 "照片與 OCR",
07-SECURITY.md section 4):

    POST /uploads   multipart, batch <=30 photos, per-file <=15MB, magic-byte
                     validated, Pillow re-encoded (EXIF stripped), AES-256-GCM
                     encrypted at rest.
    GET  /uploads/{id}  authorized decrypt-and-stream back; confidential-item
                     photos are restricted to admin/counter.

Uploaded photos are not yet attached to any `mail_items` row at upload time
(the counter photographs the label *before* the OCR draft is confirmed into
a real item) -- there is no FK on `attachments.owner_id`, so each attachment
is created "self-owned" (`owner_id == attachment.id`) as a "pending, not yet
linked to a real record" marker. Wiring a confirmed `mail_items` row back to
its attachments (reassigning `owner_id`) is the counter-confirmation flow's
job and out of this milestone's scope (see the M2-01 completion report for
this documented deviation). A pending/self-owned attachment is therefore
treated the same as a confidential one for `GET /uploads/{id}` authorization
-- only admin/counter (the roles that can create it) may read it back.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok
from app.db import get_session
from app.models.attachment import Attachment
from app.models.enums import AttachmentKind, AttachmentOwnerType, UserRole
from app.models.user import User
from app.security.csrf import require_csrf
from app.security.file_crypto import read_encrypted_file, save_encrypted_file
from app.security.image_ops import (
    InvalidImageError,
    extension_for_mime,
    extract_capture_time,
    output_mime_for,
    reencode_strip_exif,
    sniff_image_mime,
)
from app.security.rbac import require_role
from app.security.upload_limits import MAX_UPLOAD_FILE_BYTES, MAX_UPLOAD_FILES
from app.services.audit import record_audit
from app.services.confidential import resolve_is_confidential

router = APIRouter(prefix="/uploads", tags=["uploads"], dependencies=[Depends(require_csrf)])

WRITE_ROLES = (UserRole.admin, UserRole.counter)
READ_ROLES = (UserRole.admin, UserRole.counter, UserRole.viewer)
CONFIDENTIAL_ROLES = (UserRole.admin, UserRole.counter)


def _bad_type(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "UPLOAD_BAD_TYPE", "message": message})


def _too_large(message: str) -> HTTPException:
    return HTTPException(status_code=413, detail={"code": "UPLOAD_TOO_LARGE", "message": message})


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404, detail={"code": "NOT_FOUND", "message": "Attachment not found"}
    )


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    chunk_size = 64 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise _too_large(
                f"'{file.filename or 'file'}' exceeds the {max_bytes} byte per-file limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _serialize(attachment: Attachment) -> dict[str, Any]:
    return {
        "id": attachment.id,
        "kind": attachment.kind.value,
        "mime": attachment.mime,
        "size_bytes": attachment.size_bytes,
        "width": attachment.width,
        "height": attachment.height,
        "captured_at": (
            attachment.captured_at.isoformat() if attachment.captured_at else None
        ),
        "sha256": attachment.sha256,
    }


@router.post("", status_code=201)
async def upload_photos(
    request: Request,
    files: list[UploadFile] = File(...),
    kind: AttachmentKind = Form(default=AttachmentKind.label_photo),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    if not files:
        raise _bad_type("At least one file is required")
    if len(files) > MAX_UPLOAD_FILES:
        raise _too_large(f"A batch may contain at most {MAX_UPLOAD_FILES} files")

    created: list[Attachment] = []
    for upload in files:
        raw = await _read_capped(upload, MAX_UPLOAD_FILE_BYTES)
        if not raw:
            raise _bad_type(f"'{upload.filename or 'file'}' is empty")

        # Magic bytes only -- 07-SECURITY.md section 4: never trust the
        # client-declared filename/Content-Type.
        mime = sniff_image_mime(raw)
        if mime is None:
            raise _bad_type(
                f"'{upload.filename or 'file'}' is not a recognized image "
                "(allowed: image/jpeg, image/png, image/webp, image/heic)"
            )

        # Read the capture time out of EXIF *first* -- reencode_strip_exif
        # below deliberately destroys the EXIF block (GPS is personal data).
        captured_at = extract_capture_time(raw, mime)

        try:
            sanitized, width, height = reencode_strip_exif(raw, mime)
        except InvalidImageError as exc:
            raise _bad_type(f"'{upload.filename or 'file'}' could not be decoded: {exc}") from exc

        # HEIC is transcoded to JPEG by reencode_strip_exif; store/serve it as
        # its *output* mime so `GET /uploads/{id}` returns something the
        # browser can render (heic in an <img> = broken image).
        out_mime = output_mime_for(mime)
        stored = save_encrypted_file(
            sanitized, subdir="mail_photos/pending", extension=extension_for_mime(out_mime)
        )

        attachment = Attachment(
            owner_type=AttachmentOwnerType.mail_item,
            # Placeholder until confirmed into a real mail_item (see module
            # docstring) -- overwritten below once the row has an id.
            owner_id="pending",
            kind=kind,
            file_path=stored["file_path"],
            sha256=stored["sha256"],
            mime=out_mime,
            size_bytes=stored["size_bytes"],
            width=width,
            height=height,
            captured_at=captured_at,
        )
        session.add(attachment)
        await session.flush()
        attachment.owner_id = attachment.id
        created.append(attachment)

    await record_audit(
        session,
        request=request,
        actor=user,
        action="attachment.upload",
        target_type="attachment",
        target_id=None,
        diff={"attachment_ids": [a.id for a in created], "count": len(created)},
    )
    await session.commit()
    for attachment in created:
        await session.refresh(attachment)

    return ok({"attachments": [_serialize(a) for a in created]})


@router.get("/{attachment_id}")
async def get_upload(
    attachment_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*READ_ROLES)),
):
    attachment = await session.get(Attachment, attachment_id)
    if attachment is None:
        raise _not_found()

    is_confidential = await resolve_is_confidential(session, attachment)
    if (is_confidential is None or is_confidential) and user.role not in CONFIDENTIAL_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FORBIDDEN",
                "message": "This photo may only be viewed by admin/counter",
            },
        )

    if is_confidential:
        await record_audit(
            session,
            request=request,
            actor=user,
            action="attachment.view_confidential",
            target_type="attachment",
            target_id=attachment.id,
        )
        await session.commit()

    plaintext = read_encrypted_file(attachment.file_path)
    ext = extension_for_mime(attachment.mime)
    headers = {"Content-Disposition": f'inline; filename="{attachment.id}.{ext}"'}
    return Response(content=plaintext, media_type=attachment.mime, headers=headers)
