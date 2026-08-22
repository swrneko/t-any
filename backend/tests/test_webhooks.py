from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.db import Database
from app.secrets import load_or_create_secret
from app.worker import Worker
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import SttStub


class WebhookStub:
    """Whatever the operator pointed WEBHOOK_URL at."""

    def __init__(self, status: int = 200) -> None:
        self.deliveries: list[dict[str, Any]] = []
        self.authorizations: list[str | None] = []
        self.app = FastAPI()

        @self.app.post("/hook")
        async def hook(request: Request) -> dict[str, str]:
            self.deliveries.append(await request.json())
            self.authorizations.append(request.headers.get("Authorization"))
            if status >= 400:
                raise RuntimeError("the receiving end is having a bad day")
            return {"ok": "thanks"}

    def http_client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=self.app))


async def run_worker(settings: Settings, stub: SttStub, hook: WebhookStub) -> None:
    database = Database(settings.db_path)
    worker = Worker(
        settings,
        database,
        load_or_create_secret(settings.secret_key_path),
        stt_factory=lambda _provider: stub.http_client(),
        webhook_factory=hook.http_client,
    )
    try:
        await worker.run_once()
    finally:
        await database.dispose()


def settings_with_hook(tmp_path: Path, **overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "data_dir": tmp_path,
        "stt_base_url": "http://speaches.test/v1",
        "stt_model": "Systran/faster-whisper-small",
        "webhook_url": "http://automation.test/hook",
        "_env_file": None,
    }
    return Settings(**{**defaults, **overrides})  # type: ignore[arg-type]


async def upload(client: AsyncClient, audio: Path) -> dict:  # type: ignore[type-arg]
    await client.post("/api/setup", json=ADMIN_CREDENTIALS)
    await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
    with audio.open("rb") as handle:
        return (
            await client.post("/api/jobs", files={"file": ("standup.wav", handle, "audio/wav")})
        ).json()


async def test_a_finished_job_is_posted_with_its_text(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_hook(tmp_path)
    hook = WebhookStub()

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)

        await run_worker(settings, SttStub(), hook)

    assert len(hook.deliveries) == 1
    delivered = hook.deliveries[0]
    assert delivered["event"] == "job.done"
    assert delivered["job"]["id"] == job["id"]
    assert delivered["job"]["title"] == "standup.wav"
    assert delivered["text"] == "Hello there. General Kenobi."


async def test_a_failed_job_says_why_and_carries_no_text(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = Settings(
        data_dir=tmp_path, webhook_url="http://automation.test/hook", _env_file=None
    )
    hook = WebhookStub()

    async with running_client(settings) as client:
        await upload(client, sample_audio)

        await run_worker(settings, SttStub(), hook)

    delivered = hook.deliveries[0]
    assert delivered["event"] == "job.failed"
    assert delivered["job"]["error_code"] == "no_stt_provider"
    assert "text" not in delivered


async def test_the_secret_travels_as_a_bearer_token(tmp_path: Path, sample_audio: Path) -> None:
    """Otherwise the receiving end has no way to tell our POST from anyone's."""
    settings = settings_with_hook(tmp_path, webhook_secret="hunter2")
    hook = WebhookStub()

    async with running_client(settings) as client:
        await upload(client, sample_audio)

        await run_worker(settings, SttStub(), hook)

    assert hook.authorizations == ["Bearer hunter2"]


async def test_a_receiver_that_is_down_does_not_undo_the_work(
    tmp_path: Path, sample_audio: Path
) -> None:
    """The transcript exists whether or not anyone was listening."""
    settings = settings_with_hook(tmp_path)
    hook = WebhookStub(status=500)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)

        await run_worker(settings, SttStub(), hook)

        finished = (await client.get(f"/api/jobs/{job['id']}")).json()

    assert finished["status"] == "done"


async def test_nothing_is_sent_when_no_hook_is_configured(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_hook(tmp_path, webhook_url=None)
    hook = WebhookStub()

    async with running_client(settings) as client:
        await upload(client, sample_audio)

        await run_worker(settings, SttStub(), hook)

    assert hook.deliveries == []
