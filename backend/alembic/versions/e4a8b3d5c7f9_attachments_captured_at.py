"""attachments.captured_at (EXIF capture time)

Revision ID: e4a8b3d5c7f9
Revises: d3f7a2c9b6e1
Create Date: 2026-07-16

The EXIF block is stripped from every upload (GPS = personal data,
07-SECURITY.md section 4), but the counter needs to know when a photo was
actually taken -- it can differ from `received_at` when a batch is uploaded
later. `extract_capture_time` lifts DateTimeOriginal out before the strip and
it lands here. Nullable: most images have no EXIF, and rows created before
this migration have no capture time to backfill.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4a8b3d5c7f9"
down_revision: Union[str, Sequence[str], None] = "d3f7a2c9b6e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attachments", "captured_at")
