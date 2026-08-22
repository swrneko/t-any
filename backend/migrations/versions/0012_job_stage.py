"""job stage

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.models  # noqa: F401  -- custom column types are rendered fully qualified

revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('stage', sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column('jobs', 'stage')
