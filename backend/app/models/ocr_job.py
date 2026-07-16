from __future__ import annotations

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import OcrStatus
from app.models.types import sa_enum


class OcrJob(Base, IdMixin, TimestampMixin):
    __tablename__ = "ocr_jobs"

    attachment_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[OcrStatus] = mapped_column(
        sa_enum(OcrStatus), nullable=False, default=OcrStatus.queued, index=True
    )
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    barcode_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
