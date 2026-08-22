from datetime import timedelta
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from app.config import Settings
from app.db import Database
from app.models import Share, utcnow
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import SttStub
from tests.test_url_ingest import run_worker_once, settings_with_stt


async def shared_job(client: AsyncClient, audio: Path, settings: Settings) -> tuple[dict, dict]:  # type: ignore[type-arg]
    await client.post("/api/setup", json=ADMIN_CREDENTIALS)
    await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
    with audio.open("rb") as handle:
        job = (
            await client.post("/api/jobs", files={"file": ("standup.wav", handle, "audio/wav")})
        ).json()
    await run_worker_once(settings, SttStub())
    share = (await client.post(f"/api/jobs/{job['id']}/share", json={})).json()
    return job, share


async def test_a_shared_transcript_is_readable_without_an_account(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job, share = await shared_job(client, sample_audio, settings)

        # A fresh client: no cookie, no session, nothing but the token.
        async with running_client(settings) as stranger:
            response = await stranger.get(f"/api/public/shares/{share['token']}")

        assert response.status_code == 200
        public = response.json()
        assert public["title"] == "standup.wav"
        assert public["text"] == "Hello there. General Kenobi."
        assert [segment["text"] for segment in public["segments"]] == [
            "Hello there.",
            "General Kenobi.",
        ]
        assert public["job_id"] == job["id"]


async def test_sharing_twice_hands_back_the_same_link(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Two live links for one transcript means two things to revoke, and nobody
    keeps track of the second one."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job, share = await shared_job(client, sample_audio, settings)

        again = (await client.post(f"/api/jobs/{job['id']}/share", json={})).json()

        assert again["token"] == share["token"]


async def test_revoking_the_link_closes_the_door(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job, share = await shared_job(client, sample_audio, settings)

        assert (await client.delete(f"/api/jobs/{job['id']}/share")).status_code == 204

        async with running_client(settings) as stranger:
            gone = await stranger.get(f"/api/public/shares/{share['token']}")

        assert gone.status_code == 404
        assert gone.json()["error"]["code"] == "share_not_found"


async def test_an_expired_link_says_so_rather_than_pretending_it_never_existed(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Written straight into the database on purpose: the alternative is faking
    the clock, and expiry is the one thing here that only time can trigger."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        _, share = await shared_job(client, sample_audio, settings)

    database = Database(settings.db_path)
    async with database.session_factory() as session:
        row = await session.scalar(select(Share).where(Share.token == share["token"]))
        assert row is not None
        row.expires_at = utcnow() - timedelta(minutes=1)
        await session.commit()
    await database.dispose()

    async with running_client(settings) as stranger:
        response = await stranger.get(f"/api/public/shares/{share['token']}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "share_expired"


async def test_a_share_can_be_given_a_lifetime(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
        with sample_audio.open("rb") as handle:
            job = (
                await client.post(
                    "/api/jobs", files={"file": ("standup.wav", handle, "audio/wav")}
                )
            ).json()
        await run_worker_once(settings, SttStub())

        share = (
            await client.post(f"/api/jobs/{job['id']}/share", json={"expires_in_days": 7})
        ).json()

        assert share["expires_at"] is not None


async def test_a_token_nobody_issued_is_not_found(tmp_path: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        response = await client.get("/api/public/shares/definitely-not-a-real-token")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "share_not_found"


async def test_a_shared_transcript_can_be_exported_by_anyone_holding_the_link(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        _, share = await shared_job(client, sample_audio, settings)

        async with running_client(settings) as stranger:
            response = await stranger.get(
                f"/api/public/shares/{share['token']}/export", params={"format": "srt"}
            )

        assert response.status_code == 200
        assert response.text.startswith("1\n00:00:00,000 --> 00:00:01,400\n")


async def test_the_audio_travels_with_the_link_so_the_player_works(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        _, share = await shared_job(client, sample_audio, settings)

        async with running_client(settings) as stranger:
            response = await stranger.get(f"/api/public/shares/{share['token']}/audio")

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/ogg"


async def test_a_share_link_previews_itself_when_pasted_somewhere(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Thirty lines of meta tags instead of a server-rendering framework: the
    only page anyone links to from outside is this one."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><head><title>t</title></head><body></body></html>")
    settings = settings_with_stt(tmp_path, frontend_dist=dist)

    async with running_client(settings) as client:
        _, share = await shared_job(client, sample_audio, settings)

        page = await client.get(f"/s/{share['token']}")

        assert page.status_code == 200
        assert 'property="og:title" content="standup.wav"' in page.text
        assert "og:description" in page.text


async def test_a_bad_token_still_gets_the_app_rather_than_a_stack_trace(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><head></head><body>spa</body></html>")
    settings = settings_with_stt(tmp_path, frontend_dist=dist)

    async with running_client(settings) as client:
        page = await client.get("/s/nope")

        assert page.status_code == 200
        assert "og:title" not in page.text


async def test_only_the_owner_can_share_a_transcript(tmp_path: Path, sample_audio: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", _env_file=None)

    async with running_client(settings) as client:
        with sample_audio.open("rb") as handle:
            job = (
                await client.post(
                    "/api/jobs",
                    files={"file": ("standup.wav", handle, "audio/wav")},
                    headers={"X-Remote-User": "marina"},
                )
            ).json()

        response = await client.post(
            f"/api/jobs/{job['id']}/share", json={}, headers={"X-Remote-User": "pavel"}
        )

        assert response.status_code == 404
