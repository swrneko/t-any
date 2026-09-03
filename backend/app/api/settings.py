"""Instance-wide settings: what is kept, what it costs, and who gets told."""

import httpx
from fastapi import APIRouter, Request

from app.deps import AdminDep, SecretDep, SessionDep, SettingsDep
from app.errors import ApiError
from app.retention import read_policy, usage, write_policy
from app.schemas import Retention, StorageOut, WebhookIn, WebhookOut, WebhookTestOut
from app.webhooks import Webhook, present, read_webhook, write_webhook

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/retention")
async def read_retention(_admin: AdminDep, session: SessionDep) -> Retention:
    return await read_policy(session)


@router.put("/retention")
async def update_retention(
    body: Retention, _admin: AdminDep, session: SessionDep
) -> Retention:
    return await write_policy(session, body)


@router.get("/webhook")
async def read_hook(_admin: AdminDep, session: SessionDep, secret: SecretDep) -> WebhookOut:
    return present(await read_webhook(session, secret))


@router.put("/webhook")
async def update_hook(
    body: WebhookIn, _admin: AdminDep, session: SessionDep, secret: SecretDep
) -> WebhookOut:
    stored = await read_webhook(session, secret)

    # Absent leaves the secret alone, "" clears it, anything else replaces it:
    # the mask this API hands out is never accepted back.
    if body.secret is None:
        kept = stored.secret
    else:
        kept = body.secret or None

    hook = Webhook(url=(body.url or "").strip() or None, secret=kept)
    await write_webhook(session, secret, hook)
    return present(hook)


@router.post("/webhook/test")
async def test_hook(
    request: Request, _admin: AdminDep, session: SessionDep, secret: SecretDep
) -> WebhookTestOut:
    """Send the receiver something to look at.

    The real hook fires once, is never retried, and only when a recording
    finishes -- which makes "did I type the address right" a question that
    otherwise costs a whole transcription to answer.
    """
    hook = await read_webhook(session, secret)
    if not hook.url:
        raise ApiError(422, "no_webhook", "There is no address to call yet.")

    factory = getattr(request.app.state, "webhook_client_factory", httpx.AsyncClient)
    headers = {"Authorization": f"Bearer {hook.secret}"} if hook.secret else {}

    try:
        async with factory() as http:
            response = await http.post(
                hook.url,
                json={"event": "test", "job": None},
                headers=headers,
                timeout=10.0,
            )
    except Exception:  # noqa: BLE001 -- every failure here is the same answer
        return WebhookTestOut(delivered=False, error_code="webhook_unreachable")

    if response.status_code >= 400:
        return WebhookTestOut(
            delivered=False, status=response.status_code, error_code="webhook_rejected"
        )
    return WebhookTestOut(delivered=True, status=response.status_code)


@router.get("/storage")
async def read_storage(_admin: AdminDep, settings: SettingsDep) -> StorageOut:
    """Read from disk rather than from a counter: the number exists to answer
    "where did the space go", and a counter that drifts answers nothing."""
    return usage(settings)
