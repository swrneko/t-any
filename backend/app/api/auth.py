from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import CurrentUserDep, SessionDep, SessionUserDep, SettingsDep, is_admin
from app.errors import ApiError
from app.models import User
from app.schemas import PasswordChange, UserOut
from app.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    # Deliberately unvalidated: applying the signup rules here would answer
    # "is this a valid password shape?" to anyone probing the login form.
    username: str
    password: str


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> UserOut:
    user = await session.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise ApiError(401, "invalid_credentials", "Invalid username or password.")

    signer = request.app.state.sessions
    response.set_cookie(
        settings.session_cookie_name,
        signer.issue(user.id),
        max_age=signer.max_age_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204)
async def logout(response: Response, settings: SettingsDep) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me")
async def current_user(user: CurrentUserDep, settings: SettingsDep) -> UserOut:
    # The effective answer, not the column: an admin named in the environment is
    # an admin, and the UI decides what to show from this.
    return UserOut.model_validate(user).model_copy(update={"is_admin": is_admin(user, settings)})


@router.post("/password", status_code=204)
async def change_password(
    payload: PasswordChange,
    user: SessionUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    """Changing your own password. A session only -- never a token.

    The current one is asked for even though the session already proves who is
    asking: a browser left open is exactly the case this defends against.
    """
    if settings.auth_mode != "builtin":
        raise ApiError(
            409,
            "accounts_are_external",
            "Identity comes from outside this service in this mode.",
        )
    if not verify_password(payload.current_password, user.password_hash):
        raise ApiError(401, "invalid_credentials", "That is not the current password.")

    user.password_hash = hash_password(payload.new_password)
    await session.commit()
