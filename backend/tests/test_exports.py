from pathlib import Path
from typing import Any

from httpx import AsyncClient

from app.config import Settings
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import SttStub
from tests.test_url_ingest import run_worker_once, settings_with_stt

GAPPED_TRANSCRIPT: dict[str, Any] = {
    "task": "transcribe",
    "language": "en",
    "duration": 30.0,
    "text": "First thought. Still the same thought. A new subject entirely.",
    "segments": [
        {"id": 0, "start": 0.0, "end": 2.0, "text": " First thought."},
        {"id": 1, "start": 2.1, "end": 4.0, "text": " Still the same thought."},
        {"id": 2, "start": 12.0, "end": 15.0, "text": " A new subject entirely."},
    ],
}


async def transcribed(client: AsyncClient, audio: Path, stub: SttStub, settings: Settings) -> dict:  # type: ignore[type-arg]
    await client.post("/api/setup", json=ADMIN_CREDENTIALS)
    await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
    with audio.open("rb") as handle:
        job = (
            await client.post("/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")})
        ).json()
    await run_worker_once(settings, stub)
    return job


async def test_srt_carries_numbered_cues_with_comma_milliseconds(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)

        response = await client.get(f"/api/jobs/{job['id']}/export", params={"format": "srt"})

        assert response.status_code == 200
        assert response.text == (
            "1\n"
            "00:00:00,000 --> 00:00:01,400\n"
            "Hello there.\n"
            "\n"
            "2\n"
            "00:00:01,400 --> 00:00:03,000\n"
            "General Kenobi.\n"
        )


async def test_vtt_is_srt_with_a_header_and_dots(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)

        response = await client.get(f"/api/jobs/{job['id']}/export", params={"format": "vtt"})

        assert response.text.startswith("WEBVTT\n\n")
        assert "00:00:01.400 --> 00:00:03.000" in response.text


async def test_plain_text_breaks_paragraphs_at_pauses(tmp_path: Path, sample_audio: Path) -> None:
    """A wall of text is unreadable, and the only structure a transcript has is
    where the speaker stopped talking."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(
            client, sample_audio, SttStub(payload=GAPPED_TRANSCRIPT), settings
        )

        response = await client.get(f"/api/jobs/{job['id']}/export", params={"format": "txt"})

        assert response.text == (
            "First thought. Still the same thought.\n\nA new subject entirely.\n"
        )


async def test_timestamps_are_an_option_not_a_format(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)

        plain = await client.get(f"/api/jobs/{job['id']}/export", params={"format": "txt"})
        stamped = await client.get(
            f"/api/jobs/{job['id']}/export", params={"format": "txt", "timestamps": "true"}
        )

        assert "[00:00:00]" not in plain.text
        assert "[00:00:00] Hello there." in stamped.text


async def test_markdown_leads_with_what_the_recording_was(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)

        response = await client.get(f"/api/jobs/{job['id']}/export", params={"format": "md"})

        assert response.text.startswith("# meeting.wav\n")
        assert "- Language: en" in response.text
        assert "Hello there." in response.text


async def test_json_hands_back_the_providers_own_answer(
    tmp_path: Path, sample_audio: Path
) -> None:
    """The raw response is immutable and exports are layers on top; the json
    export is that invariant made visible."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)

        response = await client.get(f"/api/jobs/{job['id']}/export", params={"format": "json"})

        assert response.json()["task"] == "transcribe"
        assert response.json()["segments"][0]["text"] == " Hello there."


async def test_a_download_is_named_after_the_recording(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)

        response = await client.get(
            f"/api/jobs/{job['id']}/export", params={"format": "srt", "download": "true"}
        )

        assert 'filename="meeting.wav.srt"' in response.headers["content-disposition"]


async def test_an_unknown_format_is_refused_with_a_code(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)

        response = await client.get(f"/api/jobs/{job['id']}/export", params={"format": "docx"})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unsupported_format"


async def test_exporting_a_job_with_no_transcript_says_so(
    client: AsyncClient, admin: dict[str, str], sample_audio: Path
) -> None:
    await client.post("/api/auth/login", json=admin)
    with sample_audio.open("rb") as handle:
        job = (
            await client.post("/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")})
        ).json()

    response = await client.get(f"/api/jobs/{job['id']}/export", params={"format": "srt"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "transcript_not_ready"
