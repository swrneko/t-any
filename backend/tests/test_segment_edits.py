import json
from pathlib import Path
from typing import Any

from httpx import AsyncClient

from app.config import Settings
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import SttStub
from tests.test_url_ingest import run_worker_once, settings_with_stt

MISHEARD: dict[str, Any] = {
    "task": "transcribe",
    "language": "en",
    "duration": 6.0,
    "text": "The claim query uses a single update returning. Kubernetes is not involved.",
    "segments": [
        {"id": 0, "start": 0.0, "end": 3.0, "text": " The claim query uses a single update"},
        {"id": 1, "start": 3.0, "end": 6.0, "text": " returning. Kubernetes is not involved."},
    ],
}


async def transcribed(
    client: AsyncClient, audio: Path, settings: Settings, name: str = "standup.wav"
) -> dict:  # type: ignore[type-arg]
    await client.post("/api/setup", json=ADMIN_CREDENTIALS)
    await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
    with audio.open("rb") as handle:
        job = (await client.post("/api/jobs", files={"file": (name, handle, "audio/wav")})).json()
    await run_worker_once(settings, SttStub(payload=MISHEARD))
    return job


async def test_a_corrected_segment_is_what_the_transcript_and_its_exports_say(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, settings)

        response = await client.patch(
            f"/api/jobs/{job['id']}/segments/1",
            json={"text": "returning. Kubernetes is not involved here."},
        )

        assert response.status_code == 200
        assert response.json()["text"] == "returning. Kubernetes is not involved here."
        assert response.json()["edited"] is True

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        assert transcript["segments"][1]["text"].endswith("involved here.")
        assert transcript["segments"][0]["edited"] is False

        exported = await client.get(f"/api/jobs/{job['id']}/export?format=txt")
        assert "involved here." in exported.text


async def test_the_provider_s_own_answer_is_never_touched(
    tmp_path: Path, sample_audio: Path
) -> None:
    """The raw response is the one durable thing. An edit is a layer on top of
    it, which is what makes "reset" and "re-transcribe, keep my corrections"
    possible at all."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, settings)
        await client.patch(f"/api/jobs/{job['id']}/segments/0", json={"text": "Something else"})

        raw = await client.get(f"/api/jobs/{job['id']}/export?format=json")

    assert json.loads(raw.text) == MISHEARD


async def test_an_empty_correction_gives_the_original_back(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, settings)
        await client.patch(f"/api/jobs/{job['id']}/segments/0", json={"text": "Something else"})

        restored = await client.patch(f"/api/jobs/{job['id']}/segments/0", json={"text": "   "})

        assert restored.json()["text"] == "The claim query uses a single update"
        assert restored.json()["edited"] is False


async def test_search_follows_the_correction(tmp_path: Path, sample_audio: Path) -> None:
    """The whole point of a searchable archive is that it holds what the
    recording says, not what the model heard."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, settings)

        await client.patch(
            f"/api/jobs/{job['id']}/segments/1",
            json={"text": "returning. Postgres is not involved."},
        )

        found = (await client.get("/api/search", params={"q": "Postgres"})).json()
        assert [hit["job_id"] for hit in found] == [job["id"]]

        gone = (await client.get("/api/search", params={"q": "Kubernetes"})).json()
        assert gone == []


async def test_a_segment_that_is_not_there_says_so(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, settings)

        response = await client.patch(f"/api/jobs/{job['id']}/segments/99", json={"text": "hi"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "segment_not_found"


async def test_a_reader_of_a_share_cannot_correct_anything(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, settings)
        token = (await client.post(f"/api/jobs/{job['id']}/share", json={})).json()["token"]

    async with running_client(settings) as reader:
        response = await reader.patch(
            f"/api/jobs/{job['id']}/segments/0", json={"text": "vandalism"}
        )
        shared = await reader.get(f"/api/public/shares/{token}")

    assert response.status_code == 401
    assert shared.status_code == 200
