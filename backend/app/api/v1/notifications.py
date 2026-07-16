"""POST /items/{id}/notify -- manual resend (03-API-SPEC.md section 2
"收件": "POST /items/{id}/notify 手動重发通知"). Counter-facing: an item
whose notifications all went `dead` shows up in a "通知失敗" list
(05-NOTIFICATIONS.md section 5); this lets the counter re-queue and
re-attempt delivery on demand rather than waiting for the next state change.

Also GET /notifications (M3-R1 blocking #3): the list backing that same
"通知失敗" page (src/pages/notifications/NotificationFailuresPage.vue,
src/api/notifications.ts) called an endpoint that didn't exist on the
backend at all -- every load 404'd. Mounted as a second router here (its own
`/notifications` prefix, not `/items`) so both live next to the shared
`queue_notifications_for_item` domain logic they're both about.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok, paginated
from app.api.v1._common import pagination_params
from app.db import get_session
from app.models.employee import Employee
from app.models.enums import NotificationStatus, NotificationTemplate, UserRole
from app.models.mail_item import MailItem
from app.models.notification import Notification
from app.models.user import User
from app.notify.worker import launch_delivery_for_many
from app.security.csrf import require_csrf
from app.security.rbac import require_role
from app.services.audit import record_audit
from app.services.notify import queue_notifications_for_item

router = APIRouter(prefix="/items", tags=["notifications"], dependencies=[Depends(require_csrf)])

WRITE_ROLES = (UserRole.admin, UserRole.counter)
READ_ROLES = (UserRole.admin, UserRole.counter)

# app/notify/worker.py's `_already_satisfied_by_sibling` dead-letters a
# "first_success" strategy's losing rows with this error prefix. Those rows
# are an expected, benign no-op (a sibling binding already succeeded), not a
# delivery failure -- M3-R1 suggestion (adopted): they must not be mixed into
# the counter-facing "通知失敗" (dead) list below.
SKIPPED_ERROR_PREFIX = "skipped:"

notifications_list_router = APIRouter(
    prefix="/notifications", tags=["notifications"], dependencies=[Depends(require_csrf)]
)


def _serialize_notification(
    notification: Notification, *, item_no: str | None, recipient_name: str | None
) -> dict:
    return {
        "id": notification.id,
        "mail_item_id": notification.mail_item_id,
        "item_no": item_no,
        "recipient_name": recipient_name,
        "employee_id": notification.employee_id,
        "channel": notification.channel.value,
        "template": notification.template.value,
        "status": notification.status.value,
        "sent_at": notification.sent_at.isoformat() if notification.sent_at else None,
        "error": notification.error,
        "retries": notification.retries,
    }


@notifications_list_router.get("")
async def list_notifications(
    pagination: tuple[int, int] = Depends(pagination_params),
    status: NotificationStatus | None = None,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*READ_ROLES)),
):
    page, size = pagination

    # NOTE: `error IS NULL` (the common case -- most notifications never
    # error at all) must not get swept up by this exclusion. SQL's
    # three-valued logic means `error.like(...)` alone evaluates to NULL
    # (not False) when `error IS NULL`, which would make the whole `NOT(...)`
    # filter NULL too and silently exclude the row from every result set --
    # `error.isnot(None)` short-circuits the AND to a definite False first.
    base_filter = not_(
        (Notification.status == NotificationStatus.dead)
        & Notification.error.isnot(None)
        & Notification.error.like(f"{SKIPPED_ERROR_PREFIX}%")
    )

    stmt = select(Notification).where(base_filter)
    count_stmt = select(func.count()).select_from(Notification).where(base_filter)
    if status is not None:
        stmt = stmt.where(Notification.status == status)
        count_stmt = count_stmt.where(Notification.status == status)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Notification.created_at.desc()).offset((page - 1) * size).limit(size)
    rows = (await session.execute(stmt)).scalars().all()

    mail_item_ids = {r.mail_item_id for r in rows}
    employee_ids = {r.employee_id for r in rows}

    items_by_id: dict[str, MailItem] = {}
    if mail_item_ids:
        item_rows = (
            (await session.execute(select(MailItem).where(MailItem.id.in_(mail_item_ids))))
            .scalars()
            .all()
        )
        items_by_id = {i.id: i for i in item_rows}

    employees_by_id: dict[str, Employee] = {}
    if employee_ids:
        employee_rows = (
            (await session.execute(select(Employee).where(Employee.id.in_(employee_ids))))
            .scalars()
            .all()
        )
        employees_by_id = {e.id: e for e in employee_rows}

    def _item_no_for(row: Notification) -> str | None:
        item = items_by_id.get(row.mail_item_id)
        return item.item_no if item is not None else None

    def _recipient_name_for(row: Notification) -> str | None:
        employee = employees_by_id.get(row.employee_id)
        return employee.name if employee is not None else None

    data = [
        _serialize_notification(
            row,
            item_no=_item_no_for(row),
            recipient_name=_recipient_name_for(row),
        )
        for row in rows
    ]
    return paginated(data, total=total, page=page, size=size)


class ManualNotifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: NotificationTemplate = NotificationTemplate.received


@router.post("/{item_id}/notify")
async def manual_notify(
    item_id: str,
    payload: ManualNotifyRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    item = await session.get(MailItem, item_id)
    if item is None:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "Mail item not found"}
        )
    if not item.recipient_employee_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ITEM_NO_RECIPIENT",
                "message": "This item has no recipient employee to notify",
            },
        )

    created = await queue_notifications_for_item(
        session,
        mail_item_id=item.id,
        employee_id=item.recipient_employee_id,
        template=payload.template,
    )
    if not created:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NO_NOTIFICATION_BINDING",
                "message": "The recipient has no notification bindings",
            },
        )

    await record_audit(
        session,
        request=request,
        actor=user,
        action="mail_item.notify_manual",
        target_type="mail_item",
        target_id=item.id,
        diff={"template": payload.template.value, "notification_ids": [n.id for n in created]},
    )
    await session.commit()

    launch_delivery_for_many([n.id for n in created])

    return ok({"queued": [n.id for n in created]})
