"""job parts

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.models  # noqa: F401  -- custom column types are rendered fully qualified

revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Everything recorded before this was one file, which is what the default
    # says; no existing row has to be looked at.
    op.add_column(
        'jobs',
        sa.Column('parts', sa.Integer(), nullable=False, server_default='1'),
    )


def downgrade() -> None:
    op.drop_column('jobs', 'parts')
