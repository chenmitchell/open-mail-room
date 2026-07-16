"""Notification-queue hook (02-DATA-MODEL.md `notifications`, 01-REQUIREMENTS
section 2.1 step 5: "儲存 item 後寫一筆 notifications ... 無綁定則 skip").

This module only *enqueues* rows with status=queued -- callers are
responsible for committing and then launching delivery (M3-01:
app.notify.worker.launch_delivery_for_many) with the ids this returns, same
two-step shape as app/api/v1/ocr_jobs.py's create-then-launch-background-task
pattern (commit first, only start background work once the rows are
durable).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationStatus, NotificationTemplate
from app.models.notification import Notification
from app.models.notification_binding import NotificationBinding


async def queue_notifications_for_item(
    session: AsyncSession,
    *,
    mail_item_id: str,
    employee_id: str | None,
    template: NotificationTemplate = NotificationTemplate.received,
) -> list[Notification]:
    if not employee_id:
        return []

    # 01-REQUIREMENTS.md section 2.1 step 5 says "channel 依 employee
    # bindings, 無綁定則 skip" with no mention of a verified-only
    # restriction, so every existing binding queues a notification --
    # actual delivery (which might refuse to send to an unverified address)
    # is the M3 sender's concern, not this queueing hook's.
    result = await session.execute(
        select(NotificationBinding).where(NotificationBinding.employee_id == employee_id)
    )
    bindings = result.scalars().all()
    if not bindings:
        return []

    created: list[Notification] = []
    for binding in bindings:
        notification = Notification(
            mail_item_id=mail_item_id,
            employee_id=employee_id,
            channel=binding.channel,
            template=template,
            status=NotificationStatus.queued,
            # M3-01: pins this row to the specific binding it targets so the
            # delivery worker (app/notify/worker.py) sends to the exact
            # address even if the employee has more than one binding for the
            # same channel (e.g. two email addresses).
            binding_id=binding.id,
        )
        session.add(notification)
        created.append(notification)

    await session.flush()
    return created


async def queue_notifications_for_outbound(
    session: AsyncSession,
    *,
    outbound_item_id: str,
    employee_id: str | None,
    template: NotificationTemplate = NotificationTemplate.outbound_shipped,
) -> list[Notification]:
    """M4-01: sibling of `queue_notifications_for_item` for the outbound
    "shipped" transition (POST /outbound/{id}/shipped) -- notifies the
    *applicant* (`outbound_items.applicant_employee_id`), not a mail
    recipient. Same "no binding -> skip, no row written" behavior, and rows
    flow through the exact same queued/retry/dead-letter worker
    (app/notify/worker.py), just with `outbound_item_id` set instead of
    `mail_item_id` (see app/models/notification.py's docstring for the
    "exactly one of the two" invariant).
    """
    if not employee_id:
        return []

    result = await session.execute(
        select(NotificationBinding).where(NotificationBinding.employee_id == employee_id)
    )
    bindings = result.scalars().all()
    if not bindings:
        return []

    created: list[Notification] = []
    for binding in bindings:
        notification = Notification(
            outbound_item_id=outbound_item_id,
            employee_id=employee_id,
            channel=binding.channel,
            template=template,
            status=NotificationStatus.queued,
            binding_id=binding.id,
        )
        session.add(notification)
        created.append(notification)

    await session.flush()
    return created
