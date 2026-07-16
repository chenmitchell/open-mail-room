from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import AiProvider
from app.models.types import Encrypted, sa_enum


class AiProviderConfig(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_provider_configs"

    provider: Mapped[AiProvider] = mapped_column(sa_enum(AiProvider), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(
        Encrypted(1024, aad="ai_provider_configs.api_key_encrypted"), nullable=True
    )
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # M2-R1 blocking #1: opt-in escape hatch for `base_url`'s SSRF guard
    # (app/security/ssrf.py) -- default False (safe by default); an admin
    # must explicitly flip this to point base_url at a private-network
    # address (e.g. a local Ollama instance, per 04-AI-OCR.md sections 2/5).
    allow_private_network: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
