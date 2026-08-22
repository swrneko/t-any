"""Where a finished job is announced, and how that address is kept.

Stored rather than configured: the receiver of an automation hook changes more
often than anyone wants to restart a container for, and its shared secret
belongs in the encrypted column beside the provider keys rather than in a
compose file. The environment still seeds it, once, on an installation that has
never stored one.
"""

import json
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.models import InstanceSetting
from app.schemas import WebhookOut

WEBHOOK_KEY = "webhook"


@dataclass(frozen=True)
class Webhook:
    """What the worker needs: the address, and the secret in the clear."""

    url: str | None = None
    secret: str | None = None


async def read_webhook(session: AsyncSession, key: bytes) -> Webhook:
    row = await session.get(InstanceSetting, WEBHOOK_KEY)
    if row is None:
        return Webhook()

    stored = json.loads(row.value)
    token = stored.get("secret")
    return Webhook(
        url=stored.get("url") or None,
        secret=decrypt_secret(token.encode(), key) if token else None,
    )


async def write_webhook(session: AsyncSession, key: bytes, hook: Webhook) -> None:
    value = json.dumps(
        {
            "url": hook.url,
            "secret": encrypt_secret(hook.secret, key).decode() if hook.secret else None,
        }
    )
    row = await session.get(InstanceSetting, WEBHOOK_KEY)
    if row is None:
        session.add(InstanceSetting(key=WEBHOOK_KEY, value=value))
    else:
        row.value = value
    await session.commit()


def present(hook: Webhook) -> WebhookOut:
    """The secret leaves masked, exactly as a provider key does."""
    return WebhookOut(url=hook.url, secret=mask_secret(hook.secret) if hook.secret else None)
