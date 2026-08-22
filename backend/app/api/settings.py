"""Instance-wide settings: what is kept, and what it costs."""

from fastapi import APIRouter

from app.deps import AdminDep, SessionDep, SettingsDep
from app.retention import read_policy, usage, write_policy
from app.schemas import Retention, StorageOut

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/retention")
async def read_retention(_admin: AdminDep, session: SessionDep) -> Retention:
    return await read_policy(session)


@router.put("/retention")
async def update_retention(
    body: Retention, _admin: AdminDep, session: SessionDep
) -> Retention:
    return await write_policy(session, body)


@router.get("/storage")
async def read_storage(_admin: AdminDep, settings: SettingsDep) -> StorageOut:
    """Read from disk rather than from a counter: the number exists to answer
    "where did the space go", and a counter that drifts answers nothing."""
    return usage(settings)
