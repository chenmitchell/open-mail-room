from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import OutboundPayment, OutboundStatus
from app.models.types import Encrypted, UtcDateTime, sa_enum


class OutboundItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "outbound_items"

    # M4-01: the reports endpoint (GET /reports/summary) and the retention
    # sweep (app/services/retention.py) both filter/group by status alongside
    # shipped_at or department_id -- mirrors the composite-index reasoning in
    # app/models/mail_item.py.
    __table_args__ = (
        Index("ix_outbound_items_status_shipped_at", "status", "shipped_at"),
        Index("ix_outbound_items_department_id_status", "department_id", "status"),
    )

    item_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    applicant_employee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id"), nullable=True
    )
    to_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_org: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_address: Mapped[str | None] = mapped_column(
        Encrypted(1024, aad="outbound_items.to_address"), nullable=True
    )
    to_phone: Mapped[str | None] = mapped_column(
        Encrypted(255, aad="outbound_items.to_phone"), nullable=True
    )
    carrier_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("carriers.id"), nullable=True
    )
    tracking_no: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    shipped_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    payment: Mapped[OutboundPayment | None] = mapped_column(
        sa_enum(OutboundPayment), nullable=True
    )
    status: Mapped[OutboundStatus] = mapped_column(
        sa_enum(OutboundStatus), nullable=False, default=OutboundStatus.pending, index=True
    )
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
