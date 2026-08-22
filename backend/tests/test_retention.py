import uuid
from datetime import timedelta
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from app.config import Settings
from app.db import Database
from app.models import Job, utcnow
from app.secrets import load_or_create_secret
from app.worker import Worker
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import SttStub
from tests.test_exports import transcribed
from tests.test_url_ingest import settings_with_stt


async def age_job(settings: Settings, job_id: str, days: int) -> None:
    """Written straight into the database: retention is the one thing here that
    only the passage of time can trigger, and faking the clock is worse."""
    database = Database(settings.db_path)
    async with database.session_factory() as session:
        job = await session.scalar(select(Job).where(Job.id == uuid.UUID(job_id)))
        assert job is not None
        job.finished_at = utcnow() - timedelta(days=days)
        await session.commit()
    await database.dispose()


async def sweep(settings: Settings) -> tuple[int, int]:
    database = Database(settings.db_path)
    worker = Worker(settings, database, load_or_create_secret(settings.secret_key_path))
    try:
        return await worker.sweep()
    finally:
        await database.dispose()


def audio_of(settings: Settings, job_id: str) -> Path:
    return settings.media_dir / job_id / "audio.ogg"


async def set_policy(client: AsyncClient, **policy: int | None) -> None:
    body = {"audio_days": None, "job_days": None, **policy}
    response = await client.put("/api/settings/retention", json=body)
    assert response.status_code == 200


async def test_nothing_is_swept_until_somebody_asks_for_it(
    tmp_path: Path, sample_audio: Path
) -> None:
    """The default is to keep everything: an archive that quietly eats its own
    contents is the worst surprise a self-hosted service can spring."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)
        await age_job(settings, job["id"], days=3650)

        policy = (await client.get("/api/settings/retention")).json()

    freed, removed = await sweep(settings)

    assert policy == {"audio_days": None, "job_days": None}
    assert (freed, removed) == (0, 0)
    assert audio_of(settings, job["id"]).is_file()


async def test_audio_past_its_day_is_freed_and_the_words_are_kept(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)
        await set_policy(client, audio_days=7)
        await age_job(settings, job["id"], days=8)

        freed, removed = await sweep(settings)

        transcript = await client.get(f"/api/jobs/{job['id']}/transcript")
        listed = (await client.get("/api/jobs")).json()

    assert (freed, removed) == (1, 0)
    assert not audio_of(settings, job["id"]).exists()
    assert transcript.status_code == 200
    assert listed[0]["audio_bytes"] is None


async def test_a_recording_younger_than_the_policy_is_left_alone(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)
        await set_policy(client, audio_days=7)
        await age_job(settings, job["id"], days=6)

    freed, _removed = await sweep(settings)

    assert freed == 0
    assert audio_of(settings, job["id"]).is_file()


async def test_a_recording_past_the_second_policy_goes_entirely(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)
        await set_policy(client, job_days=30)
        await age_job(settings, job["id"], days=31)

        _freed, removed = await sweep(settings)

        listed = (await client.get("/api/jobs")).json()
        # The index has to follow here too, or a swept recording keeps
        # answering searches from a row that no longer exists.
        found = (await client.get("/api/search", params={"q": "Kenobi"})).json()

    assert removed == 1
    assert listed == []
    assert found == []
    assert not (settings.media_dir / job["id"]).exists()


async def test_an_unfinished_recording_is_never_swept(
    tmp_path: Path, sample_audio: Path
) -> None:
    """A queued job has no finished_at, and must not be read as infinitely old."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
        await set_policy(client, job_days=1, audio_days=1)
        with sample_audio.open("rb") as handle:
            job = (
                await client.post("/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")})
            ).json()

        _freed, removed = await sweep(settings)

        listed = (await client.get("/api/jobs")).json()

    assert removed == 0
    assert [row["id"] for row in listed] == [job["id"]]


async def test_the_policy_comes_back_the_way_it_was_set(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await client.post("/api/auth/login", json=admin)

    await set_policy(client, audio_days=30, job_days=365)
    read = await client.get("/api/settings/retention")

    assert read.json() == {"audio_days": 30, "job_days": 365}


async def test_a_reader_cannot_change_what_gets_deleted(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", _env_file=None)

    async with running_client(settings) as client:
        refused = await client.put(
            "/api/settings/retention",
            json={"audio_days": 1, "job_days": 1},
            headers={"X-Remote-User": "alice"},
        )

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "admin_required"


async def test_storage_says_where_the_space_went(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await transcribed(client, sample_audio, SttStub(), settings)

        usage = (await client.get("/api/settings/storage")).json()

    assert usage["audio_bytes"] > 0
    assert usage["recordings"] == 1
