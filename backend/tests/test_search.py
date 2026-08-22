from pathlib import Path
from typing import Any

from httpx import AsyncClient

from app.config import Settings
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import SttStub
from tests.test_url_ingest import run_worker_once, settings_with_stt

STANDUP: dict[str, Any] = {
    "task": "transcribe",
    "language": "en",
    "duration": 6.0,
    "text": "We should probe the heartbeat column instead of the HTTP port.",
    "segments": [
        {"id": 0, "start": 0.0, "end": 3.0, "text": " We should probe the heartbeat column"},
        {"id": 1, "start": 3.0, "end": 6.0, "text": " instead of the HTTP port."},
    ],
}

INTERVIEW: dict[str, Any] = {
    "task": "transcribe",
    "language": "en",
    "duration": 4.0,
    "text": "Opus was designed for speech, so the bitrate can be tiny.",
    "segments": [
        {"id": 0, "start": 0.0, "end": 4.0, "text": " Opus was designed for speech."},
    ],
}


async def transcribe(
    client: AsyncClient, audio: Path, settings: Settings, name: str, payload: dict[str, Any]
) -> dict:  # type: ignore[type-arg]
    with audio.open("rb") as handle:
        job = (
            await client.post("/api/jobs", files={"file": (name, handle, "audio/wav")})
        ).json()
    await run_worker_once(settings, SttStub(payload=payload))
    return job


async def test_a_word_finds_the_recording_it_was_said_in(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
        standup = await transcribe(client, sample_audio, settings, "standup.wav", STANDUP)
        await transcribe(client, sample_audio, settings, "interview.wav", INTERVIEW)

        response = await client.get("/api/search", params={"q": "heartbeat"})

        assert response.status_code == 200
        hits = response.json()
        assert [hit["job_id"] for hit in hits] == [standup["id"]]
        assert hits[0]["job_title"] == "standup.wav"
        assert hits[0]["start"] == 0.0
        assert "heartbeat" in hits[0]["excerpt"]


async def test_the_match_is_marked_without_handing_the_browser_markup(
    tmp_path: Path, sample_audio: Path
) -> None:
    """An excerpt is transcript text, and transcript text is whatever someone
    said. Marking the hit with control characters rather than tags means the UI
    never has to decide which angle brackets are ours."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
        await transcribe(client, sample_audio, settings, "standup.wav", STANDUP)

        hits = (await client.get("/api/search", params={"q": "heartbeat"})).json()

        assert "heartbeat" in hits[0]["excerpt"]
        assert "<" not in hits[0]["excerpt"]


async def test_a_word_nobody_said_finds_nothing(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
        await transcribe(client, sample_audio, settings, "standup.wav", STANDUP)

        assert (await client.get("/api/search", params={"q": "diarisation"})).json() == []


async def test_search_syntax_from_a_person_is_not_a_query_language(
    tmp_path: Path, sample_audio: Path
) -> None:
    """People type quotes, hyphens and the word AND. None of that should reach
    the FTS parser and come back as a 500."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
        await transcribe(client, sample_audio, settings, "standup.wav", STANDUP)

        for query in ['heart"beat', "AND OR NOT", "column -port", "*", "  "]:
            response = await client.get("/api/search", params={"q": query})
            assert response.status_code == 200


async def test_a_partial_word_still_finds_the_recording(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Search runs while someone types, so the last word is always half-typed."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
        await transcribe(client, sample_audio, settings, "standup.wav", STANDUP)

        hits = (await client.get("/api/search", params={"q": "heartb"})).json()

        assert len(hits) == 1


async def test_another_users_transcripts_are_not_searchable(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = Settings(
        data_dir=tmp_path,
        auth_mode="proxy",
        stt_base_url="http://speaches.test/v1",
        stt_model="Systran/faster-whisper-small",
        _env_file=None,
    )

    async with running_client(settings) as client:
        with sample_audio.open("rb") as handle:
            await client.post(
                "/api/jobs",
                files={"file": ("standup.wav", handle, "audio/wav")},
                headers={"X-Remote-User": "marina"},
            )
        await run_worker_once(settings, SttStub(payload=STANDUP))

        mine = await client.get(
            "/api/search", params={"q": "heartbeat"}, headers={"X-Remote-User": "marina"}
        )
        theirs = await client.get(
            "/api/search", params={"q": "heartbeat"}, headers={"X-Remote-User": "pavel"}
        )

        assert len(mine.json()) == 1
        assert theirs.json() == []
