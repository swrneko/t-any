import asyncio
import json
from pathlib import Path

from httpx import AsyncClient

from app.config import Settings
from app.db import Database
from app.secrets import load_or_create_secret
from app.worker import Worker
from tests.conftest import running_client
from tests.stubs import LlmStub, SttStub
from tests.test_summaries import drain, first_preset, settings_with_both, transcribed_job
from tests.test_worker import upload

LONG_TRANSCRIPT = {
    "language": "en",
    "text": "x",
    "segments": [
        {"start": float(i), "end": float(i) + 1, "text": f"sentence number {i} " * 12}
        for i in range(40)
    ],
}


async def summary_of(client: AsyncClient, job_id: str) -> dict:  # type: ignore[type-arg]
    preset = await first_preset(client)
    return (
        await client.post(f"/api/jobs/{job_id}/summaries", json={"preset_id": preset["id"]})
    ).json()


async def test_a_queued_summary_is_cancelled_before_a_worker_sees_it(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_both(tmp_path)
    llm = LlmStub()

    async with running_client(settings) as client:
        job = await transcribed_job(client, settings, sample_audio)
        summary = await summary_of(client, job["id"])

        cancelled = await client.post(f"/api/summaries/{summary['id']}/cancel")
        await drain(settings, SttStub(), llm)
        [after] = (await client.get(f"/api/jobs/{job['id']}/summaries")).json()

    assert cancelled.status_code == 200
    assert after["status"] == "cancelled"
    assert llm.calls == [], "nothing was asked of the model"


async def test_cancelling_a_running_summary_stops_the_work_in_flight(
    tmp_path: Path, sample_audio: Path
) -> None:
    """A stuck summary used to need deleting; the transcription path has had a
    stop button since milestone 2."""
    settings = settings_with_both(tmp_path).model_copy(update={"cancel_poll_seconds": 0.05})
    hold = asyncio.Event()
    llm = LlmStub(hold=hold)

    async with running_client(settings) as client:
        job = await transcribed_job(client, settings, sample_audio)
        summary = await summary_of(client, job["id"])

        database = Database(settings.db_path)
        worker = Worker(
            settings,
            database,
            load_or_create_secret(settings.secret_key_path),
            llm_factory=lambda _provider: llm.http_client(),
        )
        working = asyncio.create_task(worker.run_once())
        await asyncio.wait_for(llm.received.wait(), timeout=5)

        await client.post(f"/api/summaries/{summary['id']}/cancel")
        await asyncio.wait_for(working, timeout=5)

        [after] = (await client.get(f"/api/jobs/{job['id']}/summaries")).json()

    hold.set()
    await database.dispose()
    assert after["status"] == "cancelled"


async def test_a_finished_summary_cannot_be_cancelled(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_both(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed_job(client, settings, sample_audio)
        summary = await summary_of(client, job["id"])
        await drain(settings, SttStub(), LlmStub())

        refused = await client.post(f"/api/summaries/{summary['id']}/cancel")

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "summary_not_cancellable"


async def test_a_failed_summary_can_be_asked_again(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_both(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed_job(client, settings, sample_audio)
        summary = await summary_of(client, job["id"])
        await drain(settings, SttStub(), LlmStub(status=500))

        failed = (await client.get(f"/api/jobs/{job['id']}/summaries")).json()[0]
        retried = await client.post(f"/api/summaries/{summary['id']}/retry")
        await drain(settings, SttStub(), LlmStub(reply_for=lambda _i: "second time lucky"))
        [after] = (await client.get(f"/api/jobs/{job['id']}/summaries")).json()

    assert failed["status"] == "failed"
    assert retried.json()["status"] == "queued"
    assert retried.json()["error_code"] is None
    assert after["status"] == "done"
    assert after["content"] == "second time lucky"


async def test_a_retry_keeps_the_parts_that_already_came_back(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Reduce is where a local model usually chokes, and redoing seventeen
    parts to retry the last step is exactly what the stored partials prevent."""
    settings = settings_with_both(tmp_path, llm_context_tokens=300)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)
        await drain(settings, SttStub(payload=LONG_TRANSCRIPT), LlmStub())
        summary = await summary_of(client, job["id"])

        # Everything answers except the reduce, which is the streamed call.
        breaks_on_reduce = LlmStub(status_for=lambda _index: 200, fail_stream=True)
        await drain(settings, SttStub(), breaks_on_reduce)
        failed = (await client.get(f"/api/jobs/{job['id']}/summaries")).json()[0]

        await client.post(f"/api/summaries/{summary['id']}/retry")
        second = LlmStub(reply_for=lambda _i: "the whole thing, briefly")
        await drain(settings, SttStub(), second)
        [after] = (await client.get(f"/api/jobs/{job['id']}/summaries")).json()

    parts = json.loads(failed["partials_json"])
    assert failed["status"] == "failed"
    assert len(parts) > 1
    assert after["status"] == "done"
    # One call on the retry: the map results were already in hand.
    assert len(second.calls) == 1
    assert second.calls[0].stream is True


async def test_a_finished_summary_is_not_run_again(tmp_path: Path, sample_audio: Path) -> None:
    """Every run is a row of its own; asking again means asking for a new one."""
    settings = settings_with_both(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed_job(client, settings, sample_audio)
        summary = await summary_of(client, job["id"])
        await drain(settings, SttStub(), LlmStub())

        refused = await client.post(f"/api/summaries/{summary['id']}/retry")

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "summary_not_retryable"
