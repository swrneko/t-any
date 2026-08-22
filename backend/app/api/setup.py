from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.config import AuthMode
from app.deps import SessionDep, SettingsDep
from app.errors import ApiError
from app.models import User
from app.schemas import Credentials, UserOut
from app.security import hash_password

router = APIRouter(prefix="/setup", tags=["setup"])


class SetupStatus(BaseModel):
    needs_setup: bool
    auth_mode: AuthMode
    # What this instance can do, not what it has been through. Diarisation lives
    # in a container that is off by default, and the UI has to know whether to
    # offer it: a checkbox that always fails is worse than no checkbox.
    has_diarizer: bool


@router.get("/status")
async def setup_status(session: SessionDep, settings: SettingsDep) -> SetupStatus:
    has_diarizer = bool(settings.diarizer_url)

    if settings.auth_mode != "builtin":
        # Identity comes from elsewhere; there is no first admin to create.
        return SetupStatus(
            needs_setup=False, auth_mode=settings.auth_mode, has_diarizer=has_diarizer
        )

    user_count = await session.scalar(select(func.count()).select_from(User))
    return SetupStatus(
        needs_setup=user_count == 0, auth_mode=settings.auth_mode, has_diarizer=has_diarizer
    )


@router.post("", status_code=201)
async def create_first_admin(payload: Credentials, session: SessionDep) -> UserOut:
    user_count = await session.scalar(select(func.count()).select_from(User))
    if user_count:
        raise ApiError(
            409,
            "setup_already_completed",
            "Setup has already been completed. Ask an administrator to create your account.",
        )

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        is_admin=True,
    )
    session.add(user)
    await session.commit()
    return UserOut.model_validate(user)
