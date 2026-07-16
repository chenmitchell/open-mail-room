from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import NotificationChannel
from app.models.types import Encrypted, UtcDateTime, sa_enum


class NotificationBinding(Base, IdMixin, TimestampMixin):
    __tablename__ = "notification_bindings"

    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False, index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        sa_enum(NotificationChannel), nullable=False
    )
    address: Mapped[str] = mapped_column(
        Encrypted(1024, aad="notification_bindings.address"), nullable=False
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
