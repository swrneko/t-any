"""bearer tokens for scripts

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-22 15:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.models  # noqa: F401  -- custom column types are rendered fully qualified

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('api_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', app.models.UtcDateTime(), nullable=False),
    sa.Column('last_used_at', app.models.UtcDateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_tokens_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_api_tokens_token_hash'), ['token_hash'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_tokens_token_hash'))
        batch_op.drop_index(batch_op.f('ix_api_tokens_user_id'))

    op.drop_table('api_tokens')
