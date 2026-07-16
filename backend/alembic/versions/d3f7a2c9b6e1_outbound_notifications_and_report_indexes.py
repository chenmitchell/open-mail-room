"""M4-01: outbound notifications + report/retention indexes

- notifications.mail_item_id relaxed to nullable, notifications.outbound_item_id
  added (nullable FK -> outbound_items.id, indexed): a Notification row now
  targets either a mail_item (received/reminder/overdue templates) or an
  outbound_item (the new outbound_shipped template), never both -- see
  app/models/notification.py and app/notify/worker.py.
- mail_items.department_id / mail_items.carrier_id indexed: GET
  /reports/summary?group_by=department|carrier groups by these columns.
- outbound_items composite indexes (status, shipped_at) and
  (department_id, status): used by the reports endpoint and the daily
  retention sweep (app/services/retention.py).

Revision ID: d3f7a2c9b6e1
Revises: c2d5f8a1b4e7
Create Date: 2026-07-12 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd3f7a2c9b6e1'
down_revision: Union[str, Sequence[str], None] = 'c2d5f8a1b4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('notifications') as batch_op:
        batch_op.alter_column('mail_item_id', existing_type=sa.String(length=36), nullable=True)
        batch_op.add_column(sa.Column('outbound_item_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_notifications_outbound_item_id', 'outbound_items', ['outbound_item_id'], ['id']
        )
        batch_op.create_index(
            'ix_notifications_outbound_item_id', ['outbound_item_id'], unique=False
        )

    op.create_index(
        'ix_mail_items_department_id', 'mail_items', ['department_id'], unique=False
    )
    op.create_index(
        'ix_mail_items_carrier_id', 'mail_items', ['carrier_id'], unique=False
    )
    op.create_index(
        'ix_outbound_items_status_shipped_at',
        'outbound_items',
        ['status', 'shipped_at'],
        unique=False,
    )
    op.create_index(
        'ix_outbound_items_department_id_status',
        'outbound_items',
        ['department_id', 'status'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_outbound_items_department_id_status', table_name='outbound_items')
    op.drop_index('ix_outbound_items_status_shipped_at', table_name='outbound_items')
    op.drop_index('ix_mail_items_carrier_id', table_name='mail_items')
    op.drop_index('ix_mail_items_department_id', table_name='mail_items')

    with op.batch_alter_table('notifications') as batch_op:
        batch_op.drop_index('ix_notifications_outbound_item_id')
        batch_op.drop_constraint('fk_notifications_outbound_item_id', type_='foreignkey')
        batch_op.drop_column('outbound_item_id')
        batch_op.alter_column('mail_item_id', existing_type=sa.String(length=36), nullable=False)
