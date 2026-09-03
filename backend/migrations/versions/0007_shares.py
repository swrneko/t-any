"""public share links

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-22 14:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.models  # noqa: F401  -- custom column types are rendered fully qualified

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('shares',
    sa.Column('token', sa.String(length=64), nullable=False),
    sa.Column('job_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', app.models.UtcDateTime(), nullable=False),
    sa.Column('expires_at', app.models.UtcDateTime(), nullable=True),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token'),
    sa.UniqueConstraint('job_id')
    )


def downgrade() -> None:
    op.drop_table('shares')
