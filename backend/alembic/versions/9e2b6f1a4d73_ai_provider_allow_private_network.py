"""ai_provider_configs.allow_private_network

M2-R1 blocking #1: `base_url` gets an SSRF guard (app/security/ssrf.py) that
rejects private/loopback/link-local/reserved-network hosts unless this flag
is explicitly set -- the opt-in escape hatch for the documented "point
base_url at a local Ollama instance" deployment mode (04-AI-OCR.md sections
2/5). Added as a new migration rather than editing the initial schema
migration, per the fix-round instructions.

Revision ID: 9e2b6f1a4d73
Revises: 23b66761daf8
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9e2b6f1a4d73'
down_revision: Union[str, Sequence[str], None] = '23b66761daf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'ai_provider_configs',
        sa.Column(
            'allow_private_network',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ai_provider_configs', 'allow_private_network')
