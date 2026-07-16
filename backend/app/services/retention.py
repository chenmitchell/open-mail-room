"""Daily retention sweep (02-DATA-MODEL.md "保存期限工作" /
01-REQUIREMENTS.md section 4, task brief item 4):

    "每日排程:超過 retention_years(預設 5)的 mail_items/outbound_items ->
    依設定「匿名化」(清除姓名/電話/照片,保留統計欄位)或「刪除」;動作寫
    audit log。"

Shape mirrors app/notify/scheduler.py's daily reminder sweep: a plain async
function, not wired to a cron by this milestone (no scheduler process exists
yet in this single-process app) -- invoked by tests directly, or by a future
systemd timer / admin endpoint running `python -m app.services.retention`.

Configuration (both overridable via the generic `settings` table, same
precedence pattern as app/notify/templates.py -- settings override first,
then config/branding.yaml, then a hardcoded default):
    retention.years   int, default = branding["retention_years"] (5)
    retention.action  "anonymize" | "delete", default "anonymize"

Idempotency: "anonymize" stamps the row's `note` with a `RETENTION_MARKER`
prefix once processed, and every sweep excludes rows already carrying that
marker -- otherwise every row past the cutoff would be re-"anonymized" (a
no-op on the PII fields, but wasted work, and it would also re-delete
already-gone attachment files) on every single subsequent daily run forever.
"delete" needs no such marker since the row itself stops existing.

Attachments: for both actions, every Attachment row owned by the record
(`mail_item`/`pickup` for mail_items, `outbound_item` for outbound_items) is
deleted, and `app.security.file_crypto.delete_encrypted_file` removes the
underlying ciphertext from disk -- "匿名化...+attachment 實體檔刪除" applies
to *both* actions per the task brief, not just "delete".

`dry_run=True` performs no mutation at all: it only counts what *would* be
processed and records a single summary audit_logs row so an operator can see
a dry run happened and what it would have touched, without ever anonymizing/
deleting data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_branding
from app.models.attachment import Attachment
from app.models.enums import ActorType, AttachmentOwnerType
from app.models.mail_item import MailItem
from app.models.notification import Notification
from app.models.outbound_item import OutboundItem
from app.notify.settings_store import get_setting
from app.security.file_crypto import delete_encrypted_file
from app.services.audit import record_audit

RETENTION_MARKER = "[RETENTION_ANONYMIZED]"

KEY_YEARS = "retention.years"
KEY_ACTION = "retention.action"

_VALID_ACTIONS = ("anonymize", "delete")
_DAYS_PER_YEAR = 365.25


async def get_retention_years(session: AsyncSession) -> int:
    configured = await get_setting(session, KEY_YEARS, default=None)
    if configured is not None:
        try:
            return int(configured)
        except (TypeError, ValueError):
            pass
    return int(get_branding().get("retention_years", 5))


async def get_retention_action(session: AsyncSession) -> str:
    configured = await get_setting(session, KEY_ACTION, default="anonymize")
    action = str(configured).strip().lower()
    return action if action in _VALID_ACTIONS else "anonymize"


async def _delete_attachments_for(
    session: AsyncSession, *, owner_types: tuple[AttachmentOwnerType, ...], owner_id: str
) -> int:
    stmt = select(Attachment).where(
        Attachment.owner_type.in_(owner_types), Attachment.owner_id == owner_id
    )
    attachments = (await session.execute(stmt)).scalars().all()
    for attachment in attachments:
        delete_encrypted_file(attachment.file_path)
        await session.delete(attachment)
    return len(attachments)


async def _process_mail_item(
    session: AsyncSession, item: MailItem, *, action: str, now: datetime
) -> None:
    await _delete_attachments_for(
        session,
        owner_types=(AttachmentOwnerType.mail_item, AttachmentOwnerType.pickup),
        owner_id=item.id,
    )
    if action == "delete":
        notif_stmt = select(Notification).where(Notification.mail_item_id == item.id)
        for notification in (await session.execute(notif_stmt)).scalars().all():
            await session.delete(notification)
        await session.delete(item)
        return

    item.sender_name = None
    item.sender_org = None
    item.sender_phone = None
    item.recipient_name_raw = None
    item.recipient_employee_id = None
    item.picked_up_by_name = None
    item.note = f"{RETENTION_MARKER} at {now.isoformat()}"


async def _process_outbound_item(
    session: AsyncSession, item: OutboundItem, *, action: str, now: datetime
) -> None:
    await _delete_attachments_for(
        session, owner_types=(AttachmentOwnerType.outbound_item,), owner_id=item.id
    )
    if action == "delete":
        notif_stmt = select(Notification).where(Notification.outbound_item_id == item.id)
        for notification in (await session.execute(notif_stmt)).scalars().all():
            await session.delete(notification)
        await session.delete(item)
        return

    item.to_name = None
    item.to_org = None
    item.to_address = None
    item.to_phone = None
    item.applicant_employee_id = None
    item.note = f"{RETENTION_MARKER} at {now.isoformat()}"


async def run_retention_sweep(
    session: AsyncSession, *, now: datetime | None = None, dry_run: bool = False
) -> dict[str, int | str | bool]:
    now = now or datetime.now(timezone.utc)
    retention_years = await get_retention_years(session)
    action = await get_retention_action(session)
    cutoff = now - timedelta(days=retention_years * _DAYS_PER_YEAR)

    not_already_processed = or_(
        MailItem.note.is_(None), ~MailItem.note.like(f"{RETENTION_MARKER}%")
    )
    mail_stmt = select(MailItem).where(MailItem.received_at <= cutoff, not_already_processed)

    outbound_reference = func.coalesce(OutboundItem.shipped_at, OutboundItem.created_at)
    outbound_not_processed = or_(
        OutboundItem.note.is_(None), ~OutboundItem.note.like(f"{RETENTION_MARKER}%")
    )
    outbound_stmt = select(OutboundItem).where(
        outbound_reference <= cutoff, outbound_not_processed
    )

    if dry_run:
        mail_count = (
            await session.execute(
                select(func.count()).select_from(mail_stmt.subquery())
            )
        ).scalar_one()
        outbound_count = (
            await session.execute(
                select(func.count()).select_from(outbound_stmt.subquery())
            )
        ).scalar_one()
        await record_audit(
            session,
            request=None,
            actor=None,
            actor_type=ActorType.system,
            action="retention.sweep_dry_run",
            target_type="retention",
            target_id=None,
            diff={
                "dry_run": True,
                "action": action,
                "retention_years": retention_years,
                "mail_items_would_process": mail_count,
                "outbound_items_would_process": outbound_count,
            },
        )
        await session.commit()
        return {
            "dry_run": True,
            "action": action,
            "retention_years": retention_years,
            "mail_items_processed": 0,
            "outbound_items_processed": 0,
            "mail_items_would_process": mail_count,
            "outbound_items_would_process": outbound_count,
        }

    mail_items = (await session.execute(mail_stmt)).scalars().all()
    mail_processed = 0
    for item in mail_items:
        item_id = item.id
        await _process_mail_item(session, item, action=action, now=now)
        await session.flush()
        await record_audit(
            session,
            request=None,
            actor=None,
            actor_type=ActorType.system,
            action=f"mail_item.retention_{action}",
            target_type="mail_item",
            target_id=item_id,
        )
        mail_processed += 1

    outbound_items = (await session.execute(outbound_stmt)).scalars().all()
    outbound_processed = 0
    for item in outbound_items:
        item_id = item.id
        await _process_outbound_item(session, item, action=action, now=now)
        await session.flush()
        await record_audit(
            session,
            request=None,
            actor=None,
            actor_type=ActorType.system,
            action=f"outbound_item.retention_{action}",
            target_type="outbound_item",
            target_id=item_id,
        )
        outbound_processed += 1

    await record_audit(
        session,
        request=None,
        actor=None,
        actor_type=ActorType.system,
        action="retention.sweep",
        target_type="retention",
        target_id=None,
        diff={
            "dry_run": False,
            "action": action,
            "retention_years": retention_years,
            "mail_items_processed": mail_processed,
            "outbound_items_processed": outbound_processed,
        },
    )
    await session.commit()

    return {
        "dry_run": False,
        "action": action,
        "retention_years": retention_years,
        "mail_items_processed": mail_processed,
        "outbound_items_processed": outbound_processed,
    }
