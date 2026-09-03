"""Accounts, where this service is the one that keeps them.

`owner_id` has been on every row since the first migration, so a second person
gets a private archive for free; what was missing was any way to create one.
"""

import uuid

from fastapi import APIRouter
from sqlalchemy import func, select

from app.config import Settings
from app.deps import AdminDep, SessionDep, SettingsDep, is_admin
from app.errors import ApiError
from app.models import Job, User
from app.retention import forget_job, remove_media
from app.schemas import UserCreateIn, UserOut, UserPatch, UserRowOut
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    _admin: AdminDep, session: SessionDep, settings: SettingsDep
) -> list[UserRowOut]:
    rows = await session.execute(
        select(User, func.count(Job.id))
        .outerjoin(Job, Job.owner_id == User.id)
        .group_by(User.id)
        .order_by(User.created_at)
    )
    return [
        UserRowOut(
            id=user.id,
            username=user.username,
            # The effective answer: somebody named in ADMIN_USERS is an
            # administrator whether or not the column says so.
            is_admin=is_admin(user, settings),
            jobs=jobs,
        )
        for user, jobs in rows
    ]


@router.post("", status_code=201)
async def create_user(
    payload: UserCreateIn, _admin: AdminDep, session: SessionDep, settings: SettingsDep
) -> UserOut:
    _require_local_accounts(settings)

    taken = await session.scalar(select(User).where(User.username == payload.username))
    if taken is not None:
        raise ApiError(409, "username_taken", "Somebody already has that name.")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        is_admin=payload.is_admin,
    )
    session.add(user)
    await session.commit()
    return UserOut.model_validate(user)


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    payload: UserPatch,
    _admin: AdminDep,
    session: SessionDep,
    settings: SettingsDep,
) -> UserOut:
    user = await _user(session, user_id)
    fields = payload.model_dump(exclude_unset=True)

    if (password := fields.get("password")) is not None:
        _require_local_accounts(settings)
        user.password_hash = hash_password(password)

    wanted = fields.get("is_admin")
    if wanted is not None and wanted != user.is_admin:
        if not wanted:
            await _require_another_admin(session, settings, user)
        user.is_admin = wanted

    await session.commit()
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    admin: AdminDep,
    session: SessionDep,
    settings: SettingsDep,
    with_jobs: bool = False,
) -> None:
    user = await _user(session, user_id)

    if user.id == admin.id:
        # Not a safety rail so much as an obvious one: the request would
        # succeed and the reply would arrive at a session that no longer has
        # an owner.
        raise ApiError(409, "cannot_delete_self", "You cannot delete your own account.")
    if user.is_admin:
        await _require_another_admin(session, settings, user)

    jobs = list(await session.scalars(select(Job).where(Job.owner_id == user.id)))
    if jobs and not with_jobs:
        # Everything this person owns would go with them, and gigabytes of
        # somebody else's audio should not disappear on one click.
        raise ApiError(
            409,
            "user_has_jobs",
            "This account still holds recordings.",
            jobs=len(jobs),
        )

    # Explicitly rather than by cascade, so the search index follows them out.
    for job in jobs:
        await forget_job(session, job)
    await session.delete(user)
    await session.commit()

    for job in jobs:
        remove_media(settings, job.id)


async def _user(session: SessionDep, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise ApiError(404, "user_not_found", "No such account.")
    return user


def _require_local_accounts(settings: Settings) -> None:
    if settings.auth_mode != "builtin":
        raise ApiError(
            409,
            "accounts_are_external",
            "Identity comes from outside this service in this mode.",
        )


async def _require_another_admin(
    session: SessionDep, settings: Settings, user: User
) -> None:
    """Never leave the instance without anyone who can configure it.

    ADMIN_USERS counts: an instance whose administrators are named in the
    environment cannot be locked out by a demotion here.
    """
    others = await session.scalar(
        select(func.count()).select_from(User).where(User.is_admin, User.id != user.id)
    )
    if not others and not settings.admin_usernames:
        raise ApiError(409, "last_admin", "This is the only administrator left.")
