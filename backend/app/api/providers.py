import uuid

from fastapi import APIRouter, Request
from sqlalchemy import func, select, update

from app.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.deps import AdminDep, CurrentUserDep, SecretDep, SessionDep
from app.errors import ApiError
from app.models import Preset, Provider
from app.probe import ClientFactory, probe_client, probe_models
from app.schemas import ProviderIn, ProviderOut, ProviderPatch, ProviderProbeIn, ProviderProbeOut

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("")
async def list_providers(
    _user: CurrentUserDep, session: SessionDep, secret: SecretDep
) -> list[ProviderOut]:
    providers = (await session.scalars(select(Provider).order_by(Provider.created_at))).all()
    return [_present(provider, secret) for provider in providers]


@router.post("", status_code=201)
async def create_provider(
    payload: ProviderIn, _admin: AdminDep, session: SessionDep, secret: SecretDep
) -> ProviderOut:
    provider = Provider(
        kind=payload.kind,
        name=payload.name,
        base_url=payload.base_url,
        default_model=payload.default_model,
        context_tokens=payload.context_tokens,
        api_key_encrypted=encrypt_secret(payload.api_key, secret) if payload.api_key else None,
    )
    session.add(provider)
    await session.flush()

    # The first of its kind takes the job by default: an instance whose only
    # provider is not the chosen one still cannot transcribe anything.
    alone = not await _has_default(session, payload.kind, besides=provider.id)
    if payload.is_default or alone:
        await _make_default(session, provider)

    await session.commit()
    return _present(provider, secret)


@router.patch("/{provider_id}")
async def update_provider(
    provider_id: uuid.UUID,
    payload: ProviderPatch,
    _admin: AdminDep,
    session: SessionDep,
    secret: SecretDep,
) -> ProviderOut:
    provider = await _provider(session, provider_id)
    fields = payload.model_dump(exclude_unset=True)

    if (api_key := fields.pop("api_key", None)) is not None:
        provider.api_key_encrypted = encrypt_secret(api_key, secret) if api_key else None

    # Only promotion is meaningful: something has to be the default, so a bare
    # "no longer the default" would leave the kind with nobody answering.
    promote = bool(fields.pop("is_default", False))

    for name, value in fields.items():
        setattr(provider, name, value)
    if promote:
        await _make_default(session, provider)

    await session.commit()
    return _present(provider, secret)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: uuid.UUID, _admin: AdminDep, session: SessionDep) -> None:
    provider = await _provider(session, provider_id)

    if provider.kind == "stt" and not await _others_of_kind(session, provider):
        raise ApiError(
            409,
            "last_stt_provider",
            "The only speech-to-text provider cannot be removed.",
        )

    # A preset that named this provider falls back to the default, which is what
    # a preset without one does anyway.
    await session.execute(
        update(Preset).where(Preset.provider_id == provider.id).values(provider_id=None)
    )

    orphaned = provider.is_default
    kind = provider.kind
    await session.delete(provider)
    await session.flush()

    if orphaned:
        successor = await session.scalar(
            select(Provider).where(Provider.kind == kind).order_by(Provider.created_at).limit(1)
        )
        if successor is not None:
            successor.is_default = True

    await session.commit()


@router.post("/test")
async def test_provider(
    payload: ProviderProbeIn,
    request: Request,
    _admin: AdminDep,
    session: SessionDep,
    secret: SecretDep,
) -> ProviderProbeOut:
    """Answer "does anything live at this address" before a job depends on it."""
    if payload.provider_id is not None:
        provider = await _provider(session, payload.provider_id)
        base_url = provider.base_url
        api_key = (
            decrypt_secret(provider.api_key_encrypted, secret)
            if provider.api_key_encrypted
            else None
        )
    elif payload.base_url:
        base_url, api_key = payload.base_url, payload.api_key
    else:
        raise ApiError(422, "probe_without_target", "Give a provider or an address to test.")

    factory: ClientFactory = getattr(request.app.state, "probe_client_factory", probe_client)
    result = await probe_models(base_url, api_key, factory)
    return ProviderProbeOut(
        reachable=result.reachable,
        status=result.status,
        latency_ms=result.latency_ms,
        models=result.models,
        error_code=result.error_code,
    )


async def _provider(session: SessionDep, provider_id: uuid.UUID) -> Provider:
    provider = await session.get(Provider, provider_id)
    if provider is None:
        raise ApiError(404, "provider_not_found", "No such provider.")
    return provider


async def _has_default(session: SessionDep, kind: str, *, besides: uuid.UUID) -> bool:
    found = await session.scalar(
        select(func.count())
        .select_from(Provider)
        .where(Provider.kind == kind, Provider.is_default, Provider.id != besides)
    )
    return bool(found)


async def _others_of_kind(session: SessionDep, provider: Provider) -> bool:
    found = await session.scalar(
        select(func.count())
        .select_from(Provider)
        .where(Provider.kind == provider.kind, Provider.id != provider.id)
    )
    return bool(found)


async def _make_default(session: SessionDep, provider: Provider) -> None:
    """One default per kind, demoted and promoted in the same transaction.

    The partial unique index says the same thing to anyone who reaches the
    database another way; this keeps the API from ever having to meet it.
    """
    await session.execute(
        update(Provider)
        .where(Provider.kind == provider.kind, Provider.id != provider.id)
        .values(is_default=False)
    )
    provider.is_default = True


def _present(provider: Provider, secret: bytes) -> ProviderOut:
    api_key = (
        mask_secret(decrypt_secret(provider.api_key_encrypted, secret))
        if provider.api_key_encrypted
        else None
    )
    return ProviderOut(
        id=provider.id,
        kind=provider.kind,
        name=provider.name,
        base_url=provider.base_url,
        default_model=provider.default_model,
        context_tokens=provider.context_tokens,
        is_default=provider.is_default,
        api_key=api_key,
    )
