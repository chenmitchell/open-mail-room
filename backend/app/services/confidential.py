"""Shared "is this attachment confidential-or-unconfirmed" resolution.

Factored out of app/api/v1/uploads.py (which originally had the only copy of
this logic) so app/api/v1/ocr_jobs.py's `GET /ocr/jobs/{id}/draft` (M2-R1
contract gap #5: "補機密件 gating(鏡射 uploads.py)") can apply the exact
same rule instead of a hand-rolled, potentially-drifting duplicate.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment
from app.models.enums import AttachmentOwnerType
from app.models.mail_item import MailItem


async def resolve_is_confidential(session: AsyncSession, attachment: Attachment) -> bool | None:
    """Returns True/False if the attachment is linked to a real mail_item
    (whose `is_confidential` flag we can check), or None if it is still
    "pending" (self-owned, not yet confirmed into a record) -- callers treat
    None the same as True (restrict to admin/counter): an unconfirmed photo
    has no classification yet, so it defaults to the more restrictive
    reading rather than being readable-by-default."""
    if attachment.owner_id == attachment.id:
        return None
    if attachment.owner_type in (AttachmentOwnerType.mail_item, AttachmentOwnerType.pickup):
        item = await session.get(MailItem, attachment.owner_id)
        if item is not None:
            return item.is_confidential
    return None
