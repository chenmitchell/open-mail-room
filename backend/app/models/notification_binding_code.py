from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import NotificationChannel
from app.models.types import UtcDateTime, sa_enum


class NotificationBindingCode(Base, IdMixin, TimestampMixin):
    __tablename__ = "notification_binding_codes"

    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        sa_enum(NotificationChannel), nullable=False
    )
    # 6-digit numeric code, stored plaintext (short-lived, low entropy by
    # design -- it's meant to be typed by hand into a chat app -- so
    # encryption at rest buys nothing; the 10-minute expiry + single-use
    # `consumed_at` are the actual controls).
    code: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    # M3-R1 blocking #2: the code space is only 10^6 and the webhook that
    # consumes a guess has no per-employee context to scope a lockout to, so
    # every wrong guess against *any* still-outstanding code for a channel
    # charges a failed attempt against every one of those outstanding codes
    # (see app/notify/binding_codes.py `consume_binding_code`). Once a code's
    # failed_attempts reaches MAX_FAILED_ATTEMPTS it stops matching (treated
    # as invalidated) even if it hasn't expired yet -- an attacker burns down
    # a shared, small guess budget instead of getting unlimited attempts per
    # code. Migration: added as a nullable-with-default column so existing
    # rows (from before this column existed) default to 0 -- see
    # alembic/versions for the additive migration.
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
