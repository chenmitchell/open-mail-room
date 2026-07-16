from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import CarrierKind
from app.models.types import sa_enum


class Carrier(Base, IdMixin, TimestampMixin):
    __tablename__ = "carriers"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    kind: Mapped[CarrierKind] = mapped_column(sa_enum(CarrierKind), nullable=False)
    tracking_pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
