"""Searching the archive.

FTS5 is a query language, and the box a person types into is not. Everything
they write is treated as words to find, never as syntax: an unbalanced quote or
the word AND has to come back as results, not as a parser error.
"""

import re
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# The match is marked with control characters rather than tags. An excerpt is
# transcript text, which is whatever somebody said out loud -- if it contained
# "<mark>" the UI would have no way to tell that apart from a highlight of ours.
MARK_START = "\x02"
MARK_END = "\x03"

WORD = re.compile(r"[^\W_]+", re.UNICODE)

SEARCH_SQL = sa.text(
    """
    SELECT j.id AS job_id,
           j.title AS job_title,
           s.idx AS idx,
           s.start AS start,
           snippet(segments_fts, 0, :mark_start, :mark_end, '…', 12) AS excerpt
    FROM segments_fts
    JOIN segments s ON s.rowid = segments_fts.rowid
    JOIN transcripts t ON t.id = s.transcript_id
    JOIN jobs j ON j.id = t.job_id
    WHERE segments_fts MATCH :query AND j.owner_id = :owner
    ORDER BY bm25(segments_fts), j.created_at DESC, s.idx
    LIMIT :limit
    """
).bindparams(sa.bindparam("owner", type_=sa.Uuid))


@dataclass(frozen=True)
class Hit:
    job_id: uuid.UUID
    job_title: str
    idx: int
    start: float
    excerpt: str


def to_match_query(raw: str) -> str | None:
    """Turn what a person typed into something FTS5 will accept.

    Words only, each quoted so no character in it is an operator. The last one
    gets a prefix star because search runs while they are still typing it.
    """
    words = WORD.findall(raw)
    if not words:
        return None
    quoted = [f'"{word}"' for word in words[:-1]]
    quoted.append(f'"{words[-1]}"*')
    return " ".join(quoted)


async def search(session: AsyncSession, owner_id: uuid.UUID, raw: str, limit: int) -> list[Hit]:
    query = to_match_query(raw)
    if query is None:
        return []

    rows = await session.execute(
        SEARCH_SQL,
        {
            "query": query,
            "owner": owner_id,
            "limit": limit,
            "mark_start": MARK_START,
            "mark_end": MARK_END,
        },
    )
    return [
        Hit(
            job_id=uuid.UUID(str(row.job_id)),
            job_title=row.job_title,
            idx=row.idx,
            start=row.start,
            excerpt=row.excerpt,
        )
        for row in rows
    ]
