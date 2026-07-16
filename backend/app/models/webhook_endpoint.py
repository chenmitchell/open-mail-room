from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.types import Encrypted, UtcDateTime


class WebhookEndpoint(Base, IdMixin, TimestampMixin):
    __tablename__ = "webhook_endpoints"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(
        Encrypted(255, aad="webhook_endpoints.secret"), nullable=False
    )
    events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_success_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True
    )
    # Consecutive failure count -- reset to 0 on every successful delivery;
    # 20 consecutive failures auto-disables the endpoint (03-API-SPEC.md
    # section 3 "連續失敗 20 次自動停用並通知 admin").
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # M2-R1-style opt-in escape hatch for the SSRF guard (app/security/ssrf.py)
    # on admin-configured outbound webhook URLs, per 07-SECURITY.md section 5
    # "除非 admin 明示放行" -- default False (safe by default), mirrors
    # AiProviderConfig.allow_private_network.
    allow_private_network: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
