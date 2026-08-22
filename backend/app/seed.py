from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.crypto import encrypt_secret
from app.models import InstanceSetting, Preset, Provider
from app.webhooks import WEBHOOK_KEY, Webhook, write_webhook
from app.presets import BUILTIN_PRESETS


async def seed_builtin_presets(session: AsyncSession) -> None:
    """Insert any built-in preset that is not there yet.

    Matched on the key rather than counted, so a later release can add one
    without disturbing whatever the user has written themselves.
    """
    existing = set(
        (await session.scalars(select(Preset.builtin_key).where(Preset.is_builtin))).all()
    )

    missing = [preset for preset in BUILTIN_PRESETS if preset.key not in existing]
    if not missing:
        return

    session.add_all(
        Preset(
            owner_id=None,
            name=preset.name,
            description=preset.description,
            system_prompt=preset.system_prompt,
            user_template=preset.user_template,
            temperature=preset.temperature,
            output_format="markdown",
            is_builtin=True,
            builtin_key=preset.key,
        )
        for preset in missing
    )
    await session.commit()


async def seed_providers(session: AsyncSession, settings: Settings, secret: bytes) -> None:
    """Copy the environment into the database once, on an empty installation.

    Environment variables are a convenient way to arrive preconfigured, but a
    terrible way to live: changing a provider should not mean editing a file and
    restarting a container. So env seeds, and the database rules from then on.
    """
    existing = await session.scalar(select(func.count()).select_from(Provider))
    if existing:
        return

    def encrypted(api_key: str | None) -> bytes | None:
        return encrypt_secret(api_key, secret) if api_key else None

    if settings.stt_base_url:
        session.add(
            Provider(
                kind="stt",
                name="Speech to text",
                base_url=settings.stt_base_url,
                api_key_encrypted=encrypted(settings.stt_api_key),
                default_model=settings.stt_model,
                is_default=True,
            )
        )

    if settings.llm_base_url:
        session.add(
            Provider(
                kind="llm",
                name="Language model",
                base_url=settings.llm_base_url,
                api_key_encrypted=encrypted(settings.llm_api_key),
                default_model=settings.llm_model,
                context_tokens=settings.llm_context_tokens,
                is_default=True,
            )
        )

    await session.commit()


async def seed_webhook(session: AsyncSession, settings: Settings, secret: bytes) -> None:
    """Copy WEBHOOK_URL into the database once, the way a provider is copied.

    After that the stored value rules: an operator who changes the receiver in
    the UI must not have it silently reverted by an environment variable
    nobody remembered was still set.
    """
    if not settings.webhook_url:
        return
    if await session.get(InstanceSetting, WEBHOOK_KEY) is not None:
        return

    await write_webhook(
        session, secret, Webhook(url=settings.webhook_url, secret=settings.webhook_secret)
    )
