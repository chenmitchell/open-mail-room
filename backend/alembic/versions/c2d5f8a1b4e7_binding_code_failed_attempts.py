"""M3-R1 blocking #2: binding code brute-force protection

Adds notification_binding_codes.failed_attempts (default 0) -- a shared
guess-budget counter charged against every still-outstanding code for a
channel on each wrong guess (see app/notify/binding_codes.py). Purely
additive; does not touch any other migration.

Revision ID: c2d5f8a1b4e7
Revises: b1c4a9f0d3e2
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c2d5f8a1b4e7'
down_revision: Union[str, Sequence[str], None] = 'b1c4a9f0d3e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'notification_binding_codes',
        sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('notification_binding_codes', 'failed_attempts')
