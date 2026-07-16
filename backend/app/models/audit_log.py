from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, event
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, IdMixin
from app.models.enums import ActorType
from app.models.types import UtcDateTime, sa_enum


class AuditLog(Base, IdMixin):
    """Append-only audit trail. UPDATE/DELETE are blocked at the ORM level
    (see the event listeners below) -- docs/plan/02-DATA-MODEL.md requires
    this table to be insert-only.
    """

    __tablename__ = "audit_logs"

    actor_type: Mapped[ActorType] = mapped_column(sa_enum(ActorType), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    diff_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


@event.listens_for(AuditLog, "before_update")
def _deny_audit_log_update(mapper, connection, target):  # noqa: ARG001
    raise PermissionError("audit_logs is append-only: UPDATE is not allowed")


@event.listens_for(AuditLog, "before_delete")
def _deny_audit_log_delete(mapper, connection, target):  # noqa: ARG001
    raise PermissionError("audit_logs is append-only: DELETE is not allowed")
