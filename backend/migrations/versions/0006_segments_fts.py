"""full text search over segments

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-22 13:00:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The index stores its own copy of the text rather than pointing at `segments`
# with content=''. External content would index the raw column, and the searchable
# text is coalesce(edited_text, text) -- an expression, which FTS5 cannot follow.
# Rowids are kept aligned with `segments` so a hit joins straight back.
CREATE = """
CREATE VIRTUAL TABLE segments_fts USING fts5(
    text,
    tokenize = 'unicode61 remove_diacritics 2'
)
"""

BACKFILL = """
INSERT INTO segments_fts(rowid, text)
SELECT rowid, coalesce(edited_text, text) FROM segments
"""

TRIGGERS = [
    """
    CREATE TRIGGER segments_after_insert AFTER INSERT ON segments BEGIN
        INSERT INTO segments_fts(rowid, text)
        VALUES (new.rowid, coalesce(new.edited_text, new.text));
    END
    """,
    """
    CREATE TRIGGER segments_after_delete AFTER DELETE ON segments BEGIN
        DELETE FROM segments_fts WHERE rowid = old.rowid;
    END
    """,
    """
    CREATE TRIGGER segments_after_update AFTER UPDATE ON segments BEGIN
        DELETE FROM segments_fts WHERE rowid = old.rowid;
        INSERT INTO segments_fts(rowid, text)
        VALUES (new.rowid, coalesce(new.edited_text, new.text));
    END
    """,
]


def upgrade() -> None:
    op.execute(CREATE)
    op.execute(BACKFILL)
    for trigger in TRIGGERS:
        op.execute(trigger)


def downgrade() -> None:
    for name in ("segments_after_update", "segments_after_delete", "segments_after_insert"):
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    op.execute("DROP TABLE IF EXISTS segments_fts")
