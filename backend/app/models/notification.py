from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import NotificationChannel, NotificationStatus, NotificationTemplate
from app.models.types import UtcDateTime, sa_enum


class Notification(Base, IdMixin, TimestampMixin):
    __tablename__ = "notifications"

    # M4-01: a Notification row now targets *either* a mail_item (inbound
    # templates: received/reminder/overdue) *or* an outbound_item (the new
    # outbound_shipped template) -- never both. mail_item_id was NOT NULL
    # pre-M4; it is relaxed to nullable here (see
    # alembic/versions/d3f7a2c9b6e1_*.py) so an outbound-only row can leave
    # it unset. Callers are responsible for the "exactly one of
    # mail_item_id/outbound_item_id" invariant -- app.services.notify's two
    # queue_notifications_for_* functions each set exactly one -- and
    # app.notify.worker branches on which one is present.
    mail_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("mail_items.id"), nullable=True, index=True
    )
    outbound_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("outbound_items.id"), nullable=True, index=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        sa_enum(NotificationChannel), nullable=False
    )
    template: Mapped[NotificationTemplate] = mapped_column(
        sa_enum(NotificationTemplate), nullable=False
    )
    status: Mapped[NotificationStatus] = mapped_column(
        sa_enum(NotificationStatus), nullable=False, default=NotificationStatus.queued
    )
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    binding_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("notification_bindings.id"), nullable=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
