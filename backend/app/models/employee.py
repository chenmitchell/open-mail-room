from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import EmployeeStatus
from app.models.types import Encrypted, sa_enum


class Employee(Base, IdMixin, TimestampMixin):
    __tablename__ = "employees"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    aliases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id"), nullable=True
    )
    ext: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(
        Encrypted(255, aad="employees.email"), nullable=True
    )
    phone: Mapped[str | None] = mapped_column(
        Encrypted(255, aad="employees.phone"), nullable=True
    )
    status: Mapped[EmployeeStatus] = mapped_column(
        sa_enum(EmployeeStatus), nullable=False, default=EmployeeStatus.active
    )
    pickup_code: Mapped[str | None] = mapped_column(String(8), unique=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
