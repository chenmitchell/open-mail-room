"""Daily保存期限 retention sweep (02-DATA-MODEL.md "保存期限工作",
01-REQUIREMENTS.md section 4, task brief item 4): anonymize/delete +
attachment file removal + audit trail + dry-run."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.models.attachment import Attachment
from app.models.audit_log import AuditLog
from app.models.enums import (
    AttachmentKind,
    AttachmentOwnerType,
    MailType,
    OutboundStatus,
    Refrigeration,
)
from app.models.mail_item import MailItem
from app.models.outbound_item import OutboundItem
from app.notify.settings_store import set_setting
from app.security.file_crypto import save_encrypted_file
from app.services.retention import RETENTION_MARKER, run_retention_sweep


async def _old_mail_item(
    db_session, *, years=6, seq=1, with_photo=True
) -> tuple[MailItem, str | None]:
    received_at = datetime.now(timezone.utc) - timedelta(days=365 * years)
    item = MailItem(
        item_no=f"IN-RET-{seq:04d}",
        direction="inbound",
        mail_type=MailType.parcel,
        sender_name="寄件人",
        sender_org="寄件公司",
        recipient_name_raw="收件人",
        received_at=received_at,
        picked_up_by_name="代領人",
        refrigeration=Refrigeration.none,
    )
    db_session.add(item)
    await db_session.flush()

    file_path = None
    if with_photo:
        stored = save_encrypted_file(
            b"fake-photo-bytes", subdir=f"mail_photos/{item.id}", extension="jpg"
        )
        attachment = Attachment(
            owner_type=AttachmentOwnerType.mail_item,
            owner_id=item.id,
            kind=AttachmentKind.label_photo,
            file_path=stored["file_path"],
            sha256=stored["sha256"],
            mime="image/jpeg",
            size_bytes=stored["size_bytes"],
        )
        db_session.add(attachment)
        file_path = stored["file_path"]

    await db_session.commit()
    await db_session.refresh(item)
    return item, file_path


async def _old_outbound_item(db_session, *, years=6, seq=1) -> OutboundItem:
    shipped_at = datetime.now(timezone.utc) - timedelta(days=365 * years)
    item = OutboundItem(
        item_no=f"OUT-RET-{seq:04d}",
        to_name="收件方",
        to_org="收件公司",
        shipped_at=shipped_at,
        status=OutboundStatus.shipped,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


def _file_exists(relative_path: str) -> bool:
    return (Path(get_settings().upload_dir) / relative_path).exists()


async def test_dry_run_does_not_mutate_or_delete_files(db_session):
    item, file_path = await _old_mail_item(db_session, seq=1)

    stats = await run_retention_sweep(db_session, dry_run=True)
    assert stats["dry_run"] is True
    assert stats["mail_items_would_process"] == 1
    assert stats["mail_items_processed"] == 0

    refreshed = await db_session.get(MailItem, item.id)
    assert refreshed.sender_name == "寄件人"
    assert _file_exists(file_path) is True


async def test_recent_items_are_not_touched(db_session):
    await _old_mail_item(db_session, years=1, seq=2)
    stats = await run_retention_sweep(db_session)
    assert stats["mail_items_processed"] == 0


async def test_anonymize_clears_pii_deletes_files_and_records_audit(db_session):
    item, file_path = await _old_mail_item(db_session, seq=3)

    stats = await run_retention_sweep(db_session)
    assert stats["action"] == "anonymize"
    assert stats["mail_items_processed"] == 1

    refreshed = await db_session.get(MailItem, item.id)
    assert refreshed.sender_name is None
    assert refreshed.sender_org is None
    assert refreshed.recipient_name_raw is None
    assert refreshed.picked_up_by_name is None
    assert refreshed.note is not None
    assert refreshed.note.startswith(RETENTION_MARKER)
    # Statistical fields are preserved.
    assert refreshed.item_no == item.item_no
    assert refreshed.mail_type == MailType.parcel

    assert _file_exists(file_path) is False

    attachments = (
        await db_session.execute(
            select(Attachment).where(
                Attachment.owner_type == AttachmentOwnerType.mail_item,
                Attachment.owner_id == item.id,
            )
        )
    ).scalars().all()
    assert attachments == []

    audit_rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "mail_item.retention_anonymize", AuditLog.target_id == item.id
            )
        )
    ).scalars().all()
    assert len(audit_rows) == 1

    summary_rows = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "retention.sweep"))
    ).scalars().all()
    assert len(summary_rows) == 1
    assert summary_rows[0].diff_json["mail_items_processed"] == 1


async def test_second_sweep_is_idempotent(db_session):
    await _old_mail_item(db_session, seq=4)
    first = await run_retention_sweep(db_session)
    assert first["mail_items_processed"] == 1

    second = await run_retention_sweep(db_session)
    assert second["mail_items_processed"] == 0


async def test_delete_action_removes_row_and_attachments(db_session):
    await set_setting(db_session, "retention.action", "delete")
    await db_session.commit()

    item, file_path = await _old_mail_item(db_session, seq=5)
    item_id = item.id

    stats = await run_retention_sweep(db_session)
    assert stats["action"] == "delete"
    assert stats["mail_items_processed"] == 1

    assert await db_session.get(MailItem, item_id) is None
    assert _file_exists(file_path) is False

    audit_rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "mail_item.retention_delete", AuditLog.target_id == item_id
            )
        )
    ).scalars().all()
    assert len(audit_rows) == 1


async def test_outbound_items_are_processed_using_shipped_at(db_session):
    item = await _old_outbound_item(db_session, seq=6)

    stats = await run_retention_sweep(db_session)
    assert stats["outbound_items_processed"] == 1

    refreshed = await db_session.get(OutboundItem, item.id)
    assert refreshed.to_name is None
    assert refreshed.to_org is None
    assert refreshed.note is not None
    assert refreshed.note.startswith(RETENTION_MARKER)
    assert refreshed.item_no == item.item_no


async def test_retention_years_setting_overrides_branding_default(db_session):
    # Branding default is 5 years -- with the setting lowered to 1 year, a
    # 2-year-old item must now be swept even though it wouldn't be under the
    # default.
    await set_setting(db_session, "retention.years", 1)
    await db_session.commit()

    item, _file_path = await _old_mail_item(db_session, years=2, seq=7, with_photo=False)

    stats = await run_retention_sweep(db_session)
    assert stats["retention_years"] == 1
    assert stats["mail_items_processed"] == 1

    refreshed = await db_session.get(MailItem, item.id)
    assert refreshed.sender_name is None
