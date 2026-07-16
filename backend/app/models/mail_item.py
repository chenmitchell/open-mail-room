from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import MailStatus, MailType, PickupMethod, Refrigeration
from app.models.types import Encrypted, UtcDateTime, sa_enum


class MailItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "mail_items"

    # Composite indexes for the two hot query paths (M0-R1 suggestion,
    # migration backend/alembic/versions/23b66761daf8_*): the mail queue
    # filters by status and sorts by received_at, and "my items" filters by
    # (recipient_employee_id, status). Names match the migration exactly so
    # `alembic upgrade head` and `Base.metadata.create_all()` produce the
    # same schema (see tests/test_alembic_migrations.py).
    __table_args__ = (
        Index("ix_mail_items_status_received_at", "status", "received_at"),
        Index("ix_mail_items_recipient_employee_id_status", "recipient_employee_id", "status"),
    )

    item_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="inbound")
    tracking_no: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # M4-01: indexed -- GET /reports/summary?group_by=carrier groups by this
    # column, and the export endpoints filter by it.
    carrier_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("carriers.id"), nullable=True, index=True
    )
    mail_type: Mapped[MailType] = mapped_column(
        sa_enum(MailType), nullable=False, default=MailType.parcel
    )
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_org: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_phone: Mapped[str | None] = mapped_column(
        Encrypted(255, aad="mail_items.sender_phone"), nullable=True
    )
    recipient_employee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=True, index=True
    )
    recipient_name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # M4-01: indexed -- GET /reports/summary?group_by=department groups by
    # this column.
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id"), nullable=True, index=True
    )
    received_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    received_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[MailStatus] = mapped_column(
        sa_enum(MailStatus), nullable=False, default=MailStatus.received, index=True
    )
    is_confidential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_cod: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cod_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    refrigeration: Mapped[Refrigeration] = mapped_column(
        sa_enum(Refrigeration), nullable=False, default=Refrigeration.none
    )
    size_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    remind_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    picked_up_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    picked_up_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pickup_method: Mapped[PickupMethod | None] = mapped_column(
        sa_enum(PickupMethod), nullable=True
    )
    ocr_job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ocr_jobs.id"), nullable=True
    )
