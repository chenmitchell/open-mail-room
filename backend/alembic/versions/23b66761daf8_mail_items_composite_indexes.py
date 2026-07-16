"""mail_items composite indexes

M0-R1 suggestion (adopted): the queue/list views filter by status and sort
by received_at, and the "my items" view filters by
(recipient_employee_id, status) -- both were only covered by single-column
indexes, forcing extra sorts/scans on non-trivial data volumes. Added as a
new migration rather than editing the initial schema migration, per the
fix-round instructions.

Revision ID: 23b66761daf8
Revises: 1be63c0464e3
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '23b66761daf8'
down_revision: Union[str, Sequence[str], None] = '1be63c0464e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'ix_mail_items_status_received_at',
        'mail_items',
        ['status', 'received_at'],
        unique=False,
    )
    op.create_index(
        'ix_mail_items_recipient_employee_id_status',
        'mail_items',
        ['recipient_employee_id', 'status'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_mail_items_recipient_employee_id_status', table_name='mail_items')
    op.drop_index('ix_mail_items_status_received_at', table_name='mail_items')
