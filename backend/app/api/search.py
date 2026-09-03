from fastapi import APIRouter

from app.deps import CurrentUserDep, SessionDep
from app.schemas import SearchHit
from app.search import search

router = APIRouter(prefix="/search", tags=["search"])

MAX_HITS = 100


@router.get("")
async def search_transcripts(
    user: CurrentUserDep,
    session: SessionDep,
    q: str = "",
    limit: int = 50,
) -> list[SearchHit]:
    hits = await search(session, user.id, q, min(max(limit, 1), MAX_HITS))
    return [
        SearchHit(
            job_id=hit.job_id,
            job_title=hit.job_title,
            idx=hit.idx,
            start=hit.start,
            excerpt=hit.excerpt,
        )
        for hit in hits
    ]
