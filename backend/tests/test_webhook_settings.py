from pathlib import Path

from httpx import AsyncClient

from app.config import Settings
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import SttStub
from tests.test_url_ingest import settings_with_stt
from tests.test_webhooks import WebhookStub, run_worker

SECRET = "a-long-shared-secret-value"


async def signed_in(client: AsyncClient) -> None:
    await client.post("/api/setup", json=ADMIN_CREDENTIALS)
    await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)


async def test_the_environment_seeds_the_webhook_and_the_database_keeps_it(
    tmp_path: Path,
) -> None:
    """The same bargain as providers: env arrives preconfigured, the database
    rules from then on, and a change survives the next start."""
    settings = Settings(
        data_dir=tmp_path, webhook_url="http://automation.test/hook", _env_file=None
    )

    async with running_client(settings) as client:
        await signed_in(client)
        seeded = (await client.get("/api/settings/webhook")).json()
        await client.put(
            "/api/settings/webhook", json={"url": "http://elsewhere.test/hook", "secret": SECRET}
        )

    async with running_client(settings) as restarted:
        await restarted.post("/api/auth/login", json=ADMIN_CREDENTIALS)
        kept = (await restarted.get("/api/settings/webhook")).json()

    assert seeded["url"] == "http://automation.test/hook"
    assert kept["url"] == "http://elsewhere.test/hook"


async def test_the_secret_is_masked_on_the_way_out(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        await signed_in(client)
        saved = (
            await client.put(
                "/api/settings/webhook", json={"url": "http://automation.test/hook", "secret": SECRET}
            )
        ).json()

    assert saved["secret"] == "a-l…alue"


async def test_a_finished_job_calls_the_webhook_that_was_saved_here(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Nothing is in the environment: the worker reads what the UI wrote."""
    settings = settings_with_stt(tmp_path)
    hook = WebhookStub()

    async with running_client(settings) as client:
        await signed_in(client)
        await client.put(
            "/api/settings/webhook", json={"url": "http://automation.test/hook", "secret": SECRET}
        )
        with sample_audio.open("rb") as handle:
            await client.post("/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")})

    await run_worker(settings, SttStub(), hook)

    assert [delivery["event"] for delivery in hook.deliveries] == ["job.done"]
    # The real secret, not the mask the API hands out.
    assert hook.authorizations == [f"Bearer {SECRET}"]


async def test_a_test_call_reports_what_the_receiver_said(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    hook = WebhookStub()

    async with running_client(settings, webhook_client_factory=hook.http_client) as client:
        await signed_in(client)
        await client.put("/api/settings/webhook", json={"url": "http://automation.test/hook"})

        called = await client.post("/api/settings/webhook/test")

    assert called.json() == {"delivered": True, "status": 200, "error_code": None}
    assert [delivery["event"] for delivery in hook.deliveries] == ["test"]


async def test_a_test_call_to_nobody_is_an_answer_not_a_failure(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        await signed_in(client)
        # Port 9 is the discard service: nothing listens, and the refusal is instant.
        await client.put("/api/settings/webhook", json={"url": "http://127.0.0.1:9/hook"})

        called = await client.post("/api/settings/webhook/test")

    assert called.status_code == 200
    assert called.json()["delivered"] is False
    assert called.json()["error_code"] == "webhook_unreachable"


async def test_a_test_call_needs_somewhere_to_call(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        await signed_in(client)

        called = await client.post("/api/settings/webhook/test")

    assert called.status_code == 422
    assert called.json()["error"]["code"] == "no_webhook"


async def test_a_reader_cannot_point_the_webhook_somewhere_else(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", _env_file=None)

    async with running_client(settings) as client:
        refused = await client.put(
            "/api/settings/webhook",
            json={"url": "http://mine.test/hook"},
            headers={"X-Remote-User": "alice"},
        )

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "admin_required"
