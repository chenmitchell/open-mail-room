from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, IdMixin, TimestampMixin


class Setting(Base, IdMixin, TimestampMixin):
    """Key-value store, including branding overrides.

    NOTE (deviation, see report): docs/plan/02-DATA-MODEL.md says secret
    values should be encrypted at rest, but the table only has a single
    `value_json` JSON column shared by secret and non-secret settings. The
    `Encrypted` TypeDecorator in app/models/types.py wraps a String column,
    not a JSON one, so it cannot be applied directly here without changing
    the column shape. For this scaffold we store value_json as plain JSON
    and flag secrets via `is_secret`; encrypting secret values is left as a
    follow-up (e.g. serialize+encrypt into a text column when is_secret is
    true) and should be picked up before real secrets are stored here.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSON, nullable=True
    )
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
