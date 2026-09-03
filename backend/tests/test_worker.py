import asyncio
from pathlib import Path

import pytest

from app.config import Settings
from app.db import Database
from app.secrets import load_or_create_secret
from app.worker import Worker
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import SttStub


def settings_with_stt(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        stt_base_url="http://speaches.test/v1",
        stt_model="Systran/faster-whisper-small",
        _env_file=None,
    )


async def run_worker_once(settings: Settings, stub: SttStub) -> bool:
    """A worker in its own process shares nothing with the API but the volume.

    Opening a second Database against the same file is the point: it exercises
    WAL and the claim transaction the way deployment actually runs them.
    """
    database = Database(settings.db_path)
    worker = Worker(
        settings,
        database,
        load_or_create_secret(settings.secret_key_path),
        stt_factory=lambda _provider: stub.http_client(),
    )
    try:
        return await worker.run_once()
    finally:
        await database.dispose()


async def upload(client, sample_audio: Path) -> dict:  # type: ignore[no-untyped-def]
    await client.post("/api/setup", json=ADMIN_CREDENTIALS)
    await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
    with sample_audio.open("rb") as handle:
        response = await client.post(
            "/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")}
        )
    return response.json()


async def test_an_upload_becomes_a_transcript(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)
    stub = SttStub()

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)

        assert await run_worker_once(settings, stub) is True

        finished = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert finished["status"] == "done"
        assert finished["progress"] == 1.0
        assert finished["duration_sec"] == pytest.approx(3.0, abs=0.2)

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        assert transcript["language"] == "en"
        assert transcript["text"] == "Hello there. General Kenobi."
        assert [segment["text"] for segment in transcript["segments"]] == [
            "Hello there.",
            "General Kenobi.",
        ]
        assert transcript["segments"][1]["start"] == 1.4


async def test_the_normalised_audio_is_downloadable_for_the_player(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)

        missing = await client.get(f"/api/jobs/{job['id']}/audio")
        assert missing.status_code == 404

        await run_worker_once(settings, SttStub())

        audio = await client.get(f"/api/jobs/{job['id']}/audio")
        assert audio.status_code == 200
        assert audio.headers["content-type"] == "audio/ogg"
        assert len(audio.content) > 0


async def test_the_original_upload_is_gone_once_the_audio_is_normalised(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)
        await run_worker_once(settings, SttStub())

    assert (settings.media_dir / job["id"] / "audio.ogg").is_file()
    assert not (settings.tmp_dir / job["id"]).exists()


async def test_a_missing_provider_fails_the_job_with_a_translatable_code(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)  # nothing configured

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)

        await run_worker_once(settings, SttStub())

        failed = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert failed["status"] == "failed"
        assert failed["error_code"] == "no_stt_provider"


async def test_two_workers_never_take_the_same_job(tmp_path: Path, sample_audio: Path) -> None:
    """The claim pattern breaks in exactly this way, and a single-worker test
    cannot see it."""
    settings = settings_with_stt(tmp_path)
    stub = SttStub()

    async with running_client(settings) as client:
        await upload(client, sample_audio)

        outcomes = await asyncio.gather(
            run_worker_once(settings, stub), run_worker_once(settings, stub)
        )

        assert sorted(outcomes) == [False, True]
        assert len(stub.calls) == 1


async def test_two_files_become_one_recording(tmp_path: Path, sample_audio: Path) -> None:
    """The parts are joined before anything is transcribed, so the timestamps
    run through the whole meeting rather than restarting at every card."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
        with sample_audio.open("rb") as first, sample_audio.open("rb") as second:
            job = (
                await client.post(
                    "/api/jobs",
                    files=[
                        ("file", ("part-one.wav", first, "audio/wav")),
                        ("file", ("part-two.wav", second, "audio/wav")),
                    ],
                )
            ).json()

        assert await run_worker_once(settings, SttStub()) is True

        finished = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert finished["status"] == "done"
        assert finished["duration_sec"] == pytest.approx(6.0, abs=0.3)
