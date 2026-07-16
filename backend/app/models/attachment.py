from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import AttachmentKind, AttachmentOwnerType
from app.models.types import UtcDateTime, sa_enum


class Attachment(Base, IdMixin, TimestampMixin):
    __tablename__ = "attachments"

    owner_type: Mapped[AttachmentOwnerType] = mapped_column(
        sa_enum(AttachmentOwnerType), nullable=False
    )
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[AttachmentKind] = mapped_column(sa_enum(AttachmentKind), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # EXIF DateTimeOriginal lifted out before the EXIF block is stripped at
    # intake (see app/security/image_ops.extract_capture_time). Nullable: most
    # images carry no EXIF at all, and a photo without one is still valid.
    captured_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True
    )
