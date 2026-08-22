"""job batch

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.models  # noqa: F401  -- custom column types are rendered fully qualified

revision: str = '0014'
down_revision: str | None = '0013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('batch_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_jobs_batch_id'), 'jobs', ['batch_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_jobs_batch_id'), table_name='jobs')
    op.drop_column('jobs', 'batch_id')
