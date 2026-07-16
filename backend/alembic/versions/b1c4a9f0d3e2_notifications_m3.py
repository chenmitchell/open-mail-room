"""M3-01 notification system

Adds:
- notifications.binding_id / next_attempt_at / locked_at (delivery targeting
  + backoff scheduling + crash-safe orphan sweep, see app/notify/worker.py)
- webhook_endpoints.allow_private_network (SSRF opt-in, mirrors
  ai_provider_configs.allow_private_network)
- notification_binding_codes table (LINE/Telegram binding-code flow,
  05-NOTIFICATIONS.md section 3)

Revision ID: b1c4a9f0d3e2
Revises: 9e2b6f1a4d73
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1c4a9f0d3e2'
down_revision: Union[str, Sequence[str], None] = '9e2b6f1a4d73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('notifications') as batch_op:
        batch_op.add_column(sa.Column('binding_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            'fk_notifications_binding_id', 'notification_bindings', ['binding_id'], ['id']
        )

    op.add_column(
        'webhook_endpoints',
        sa.Column(
            'allow_private_network',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        'notification_binding_codes',
        sa.Column('employee_id', sa.String(length=36), nullable=False),
        sa.Column(
            'channel',
            sa.Enum(
                'line', 'telegram', 'slack', 'discord', 'email', 'webhook', 'webpush',
                name='notificationchannel', native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('code', sa.String(length=8), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_notification_binding_codes_employee_id'),
        'notification_binding_codes', ['employee_id'], unique=False,
    )
    op.create_index(
        op.f('ix_notification_binding_codes_code'),
        'notification_binding_codes', ['code'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_notification_binding_codes_code'), table_name='notification_binding_codes'
    )
    op.drop_index(
        op.f('ix_notification_binding_codes_employee_id'), table_name='notification_binding_codes'
    )
    op.drop_table('notification_binding_codes')

    op.drop_column('webhook_endpoints', 'allow_private_network')

    with op.batch_alter_table('notifications') as batch_op:
        batch_op.drop_constraint('fk_notifications_binding_id', type_='foreignkey')
        batch_op.drop_column('locked_at')
        batch_op.drop_column('next_attempt_at')
        batch_op.drop_column('binding_id')
