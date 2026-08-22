"""speakers

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.models  # noqa: F401  -- custom column types are rendered fully qualified

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('speakers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('job_id', sa.Uuid(), nullable=False),
    sa.Column('label', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=128), nullable=True),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_id', 'label', name='uq_speakers_job_label')
    )
    with op.batch_alter_table('speakers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_speakers_job_id'), ['job_id'], unique=False)

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        # Everything transcribed before this migration was transcribed without
        # diarisation, which is exactly what the default says.
        batch_op.add_column(
            sa.Column('diarize', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_column('diarize')

    with op.batch_alter_table('speakers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_speakers_job_id'))

    op.drop_table('speakers')
