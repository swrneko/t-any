"""source metadata for url ingest

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-22 12:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.models  # noqa: F401  -- custom column types are rendered fully qualified

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('author', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('published_on', sa.String(length=10), nullable=True))
        batch_op.add_column(
            sa.Column('has_thumbnail', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_column('has_thumbnail')
        batch_op.drop_column('published_on')
        batch_op.drop_column('author')
