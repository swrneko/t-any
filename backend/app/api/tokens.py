import secrets
import uuid

from fastapi import APIRouter
from sqlalchemy import delete, select

from app.deps import TOKEN_PREFIX, SessionDep, SessionUserDep, hash_token
from app.errors import ApiError
from app.models import ApiToken
from app.schemas import ApiTokenCreated, ApiTokenIn, ApiTokenOut

router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.post("", status_code=201)
async def create_token(
    body: ApiTokenIn, user: SessionUserDep, session: SessionDep
) -> ApiTokenCreated:
    """Mint a token and show it once.

    Only the hash is kept, so this response is the only time the secret exists
    anywhere we control -- losing it means making a new one, which is the point.
    """
    secret = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"

    token = ApiToken(user_id=user.id, name=body.name, token_hash=hash_token(secret))
    session.add(token)
    await session.commit()

    return ApiTokenCreated(
        id=token.id,
        name=token.name,
        created_at=token.created_at,
        last_used_at=None,
        token=secret,
    )


@router.get("")
async def list_tokens(user: SessionUserDep, session: SessionDep) -> list[ApiTokenOut]:
    rows = await session.scalars(
        select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at)
    )
    return [ApiTokenOut.model_validate(row) for row in rows]


@router.delete("/{token_id}", status_code=204)
async def revoke_token(token_id: uuid.UUID, user: SessionUserDep, session: SessionDep) -> None:
    token = await session.scalar(
        select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id)
    )
    if token is None:
        raise ApiError(404, "token_not_found", "No such token.")

    await session.execute(delete(ApiToken).where(ApiToken.id == token_id))
    await session.commit()
