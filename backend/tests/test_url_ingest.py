from pathlib import Path

from httpx import AsyncClient

from app.config import Settings
from app.db import Database
from app.secrets import load_or_create_secret
from app.worker import Worker
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import MediaStub, SttStub, write_fake_ytdlp


def settings_with_stt(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        data_dir=tmp_path,
        stt_base_url="http://speaches.test/v1",
        stt_model="Systran/faster-whisper-small",
        _env_file=None,
        **overrides,
    )


async def run_worker_once(
    settings: Settings, stt: SttStub, downloads: MediaStub | None = None
) -> bool:
    database = Database(settings.db_path)
    worker = Worker(
        settings,
        database,
        load_or_create_secret(settings.secret_key_path),
        stt_factory=lambda _provider: stt.http_client(),
        download_factory=None if downloads is None else downloads.http_client,
    )
    try:
        return await worker.run_once()
    finally:
        await database.dispose()


async def submit(client: AsyncClient, url: str) -> dict:  # type: ignore[type-arg]
    await client.post("/api/setup", json=ADMIN_CREDENTIALS)
    await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
    return (await client.post("/api/jobs/url", json={"url": url})).json()


async def test_a_direct_media_link_becomes_a_queued_job(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await client.post("/api/auth/login", json=admin)

    response = await client.post("/api/jobs/url", json={"url": "https://example.com/talk.mp3"})

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "queued"
    assert job["source_type"] == "remote_url"
    # Until the file is fetched the filename is the only name we have.
    assert job["title"] == "talk.mp3"


async def test_a_page_link_goes_to_ytdlp(client: AsyncClient, admin: dict[str, str]) -> None:
    await client.post("/api/auth/login", json=admin)

    response = await client.post(
        "/api/jobs/url", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )

    assert response.status_code == 201
    job = response.json()
    assert job["source_type"] == "ytdlp"
    assert job["source_ref"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


async def test_something_that_is_not_a_link_is_refused(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await client.post("/api/auth/login", json=admin)

    response = await client.post("/api/jobs/url", json={"url": "file:///etc/passwd"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_url"


async def test_adding_a_url_requires_a_session(client: AsyncClient) -> None:
    response = await client.post("/api/jobs/url", json={"url": "https://example.com/talk.mp3"})

    assert response.status_code == 401


async def test_a_link_into_the_servers_own_network_is_refused(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    """Otherwise anyone with an account can use the worker as a port scanner,
    or read a cloud metadata endpoint the server can reach and they cannot."""
    await client.post("/api/auth/login", json=admin)

    response = await client.post("/api/jobs/url", json={"url": "http://127.0.0.1:9000/talk.mp3"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "url_not_allowed"


async def test_the_operator_can_allow_the_local_network(tmp_path: Path) -> None:
    """A home server fetching from its own NAS is the reason this switch exists."""
    settings = Settings(data_dir=tmp_path, allow_private_network_urls=True, _env_file=None)

    async with running_client(settings) as client:
        job = await submit(client, "http://192.168.1.10/talk.mp3")

        assert job["status"] == "queued"


async def test_a_redirect_into_the_private_network_fails_the_job(tmp_path: Path) -> None:
    """The check has to survive a public link that bounces somewhere private."""
    settings = settings_with_stt(tmp_path)
    files = MediaStub({}, redirects={"/talk.wav": "http://127.0.0.1:9000/secret"})

    async with running_client(settings) as client:
        job = await submit(client, "https://files.test/talk.wav")

        await run_worker_once(settings, SttStub(), files)

        failed = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert failed["status"] == "failed"
        assert failed["error_code"] == "url_not_allowed"


async def test_a_direct_link_is_downloaded_and_transcribed(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)
    files = MediaStub({"/talk.wav": sample_audio.read_bytes()})

    async with running_client(settings) as client:
        job = await submit(client, "https://files.test/talk.wav")

        assert await run_worker_once(settings, SttStub(), files) is True

        finished = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert finished["status"] == "done"

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        assert transcript["text"] == "Hello there. General Kenobi."

    assert files.requested == ["/talk.wav"]


async def test_a_link_that_is_gone_fails_the_job_with_a_translatable_code(
    tmp_path: Path,
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await submit(client, "https://files.test/talk.wav")

        await run_worker_once(settings, SttStub(), MediaStub({}))

        failed = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert failed["status"] == "failed"
        assert failed["error_code"] == "download_failed"
        assert failed["error_params"]["status"] == 404


async def test_a_page_link_is_fetched_by_ytdlp_and_keeps_its_metadata(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(
        tmp_path,
        ytdlp_bin=str(
            write_fake_ytdlp(
                tmp_path / "bin" / "yt-dlp",
                audio=sample_audio,
                info={
                    "title": "How Opus handles speech",
                    "uploader": "Sample Channel",
                    "upload_date": "20240513",
                },
            )
        ),
    )

    async with running_client(settings) as client:
        job = await submit(client, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert job["title"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        assert await run_worker_once(settings, SttStub()) is True

        finished = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert finished["status"] == "done"
        # The link was a placeholder for a name; the extractor knows the real one.
        assert finished["title"] == "How Opus handles speech"
        assert finished["author"] == "Sample Channel"
        assert finished["published_on"] == "2024-05-13"
        assert finished["has_thumbnail"] is True

        thumbnail = await client.get(f"/api/jobs/{job['id']}/thumbnail")
        assert thumbnail.status_code == 200
        assert thumbnail.headers["content-type"] == "image/jpeg"

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        assert transcript["text"] == "Hello there. General Kenobi."


async def test_a_link_ytdlp_cannot_open_fails_the_job_with_a_translatable_code(
    tmp_path: Path,
) -> None:
    settings = settings_with_stt(
        tmp_path,
        ytdlp_bin=str(write_fake_ytdlp(tmp_path / "bin" / "yt-dlp", exit_code=1)),
    )

    async with running_client(settings) as client:
        job = await submit(client, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        await run_worker_once(settings, SttStub())

        failed = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert failed["status"] == "failed"
        assert failed["error_code"] == "ytdlp_failed"


async def test_a_job_without_a_thumbnail_says_so(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
        with sample_audio.open("rb") as handle:
            job = (
                await client.post("/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")})
            ).json()

        assert job["has_thumbnail"] is False
        assert (await client.get(f"/api/jobs/{job['id']}/thumbnail")).status_code == 404


async def test_a_download_stops_at_the_size_limit(tmp_path: Path, sample_audio: Path) -> None:
    """The limit has to bite while the body is streaming: a lying or absent
    Content-Length must not be the only thing standing between a link and a
    full disk."""
    settings = settings_with_stt(tmp_path, max_upload_size=1024)
    files = MediaStub({"/talk.wav": sample_audio.read_bytes()})

    async with running_client(settings) as client:
        job = await submit(client, "https://files.test/talk.wav")

        await run_worker_once(settings, SttStub(), files)

        failed = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert failed["status"] == "failed"
        assert failed["error_code"] == "download_too_large"
