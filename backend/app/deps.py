import hashlib
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.models import ApiToken, User, utcnow

LOCAL_USERNAME = "local"


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db.session_factory() as session:
        yield session


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_secret(request: Request) -> bytes:
    secret: bytes = request.app.state.secret
    return secret


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
SecretDep = Annotated[bytes, Depends(get_secret)]


async def resolve_user(session: AsyncSession, username: str, *, is_admin: bool) -> User:
    """Look the user up, creating the row on first sight.

    Used by the auth modes that delegate identity elsewhere: every job still
    needs a real owner_id, so an identity from outside has to land in `users`.
    """
    user = await session.scalar(select(User).where(User.username == username))
    if user is None:
        user = User(username=username, password_hash="", is_admin=is_admin)
        session.add(user)
        await session.commit()
    return user


TOKEN_PREFIX = "tany_"
BEARER = "Bearer "
# One write per token per minute at most. The point is answering "is this key
# still in use before I delete it", which a minute's resolution answers fine.
LAST_USED_RESOLUTION = timedelta(minutes=1)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def user_from_bearer(session: AsyncSession, header: str) -> User:
    """Identify the caller by an API token, in any auth mode.

    A token is an identity of its own: the whole point is that a script reaches
    the same API the browser does, on an instance where the browser's way in may
    be a reverse proxy or nothing at all.
    """
    token = await session.scalar(
        select(ApiToken).where(ApiToken.token_hash == hash_token(header.removeprefix(BEARER)))
    )
    user = await session.get(User, token.user_id) if token is not None else None
    if token is None or user is None:
        raise ApiError(401, "not_authenticated", "That token is not valid.")

    now = utcnow()
    if token.last_used_at is None or now - token.last_used_at > LAST_USED_RESOLUTION:
        token.last_used_at = now
        await session.commit()
    return user


async def get_current_user(
    request: Request, session: SessionDep, settings: SettingsDep
) -> User:
    header = request.headers.get("Authorization")
    if header and header.startswith(BEARER):
        # Checked before anything else, and never falling through to the cookie:
        # a caller who sent a token and got in as somebody else is a worse
        # surprise than a plain 401.
        request.state.authenticated_by_token = True
        return await user_from_bearer(session, header)

    if settings.auth_mode == "disabled":
        return await resolve_user(session, LOCAL_USERNAME, is_admin=True)

    if settings.auth_mode == "proxy":
        username = request.headers.get(settings.proxy_user_header)
        if not username:
            raise ApiError(401, "not_authenticated", "Sign in to continue.")
        return await resolve_user(session, username, is_admin=False)

    token = request.cookies.get(settings.session_cookie_name)
    user_id = request.app.state.sessions.read(token) if token else None
    user = await session.get(User, user_id) if user_id else None
    if user is None:
        raise ApiError(401, "not_authenticated", "Sign in to continue.")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_session_user(request: Request, user: CurrentUserDep) -> User:
    """A user who signed in, not a script holding a key.

    Managing tokens is the one thing a token may not do: otherwise a leaked key
    mints its replacement and revoking the original changes nothing.
    """
    if getattr(request.state, "authenticated_by_token", False):
        raise ApiError(403, "session_required", "Sign in to manage API tokens.")
    return user


SessionUserDep = Annotated[User, Depends(get_session_user)]
