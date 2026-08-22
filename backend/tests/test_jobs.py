from pathlib import Path

from httpx import AsyncClient

from app.config import Settings
from tests.conftest import running_client


async def test_uploading_a_file_creates_a_queued_job(
    client: AsyncClient, admin: dict[str, str], sample_audio: Path
) -> None:
    await client.post("/api/auth/login", json=admin)

    with sample_audio.open("rb") as handle:
        response = await client.post(
            "/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")}
        )

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "queued"
    assert job["title"] == "meeting.wav"


async def test_timestamps_come_back_marked_as_utc(
    client: AsyncClient, admin: dict[str, str], sample_audio: Path
) -> None:
    """SQLite drops the offset on the way in. Handing a naive timestamp to a
    browser means it renders in whatever timezone the viewer happens to be in."""
    await client.post("/api/auth/login", json=admin)
    with sample_audio.open("rb") as handle:
        created = (
            await client.post("/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")})
        ).json()

    # Read back, not the create response: only a round trip through SQLite
    # exposes the dropped offset.
    fetched = (await client.get(f"/api/jobs/{created['id']}")).json()

    assert fetched["created_at"].endswith(("Z", "+00:00"))


async def test_a_job_can_be_read_back_and_appears_in_the_list(
    client: AsyncClient, admin: dict[str, str], sample_audio: Path
) -> None:
    await client.post("/api/auth/login", json=admin)
    with sample_audio.open("rb") as handle:
        created = (
            await client.post("/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")})
        ).json()

    fetched = await client.get(f"/api/jobs/{created['id']}")
    listing = await client.get("/api/jobs")

    assert fetched.json()["id"] == created["id"]
    assert [job["id"] for job in listing.json()] == [created["id"]]


async def test_a_job_is_invisible_to_another_user(tmp_path: Path, sample_audio: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", _env_file=None)

    async with running_client(settings) as client:
        with sample_audio.open("rb") as handle:
            created = (
                await client.post(
                    "/api/jobs",
                    files={"file": ("meeting.wav", handle, "audio/wav")},
                    headers={"X-Remote-User": "marina"},
                )
            ).json()

        owner = await client.get(
            f"/api/jobs/{created['id']}", headers={"X-Remote-User": "marina"}
        )
        stranger = await client.get(
            f"/api/jobs/{created['id']}", headers={"X-Remote-User": "pavel"}
        )

        assert owner.status_code == 200
        # 404 rather than 403: whether a transcript exists is itself private.
        assert stranger.status_code == 404


async def test_uploading_requires_a_session(client: AsyncClient, sample_audio: Path) -> None:
    with sample_audio.open("rb") as handle:
        response = await client.post(
            "/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")}
        )

    assert response.status_code == 401


async def test_several_files_become_one_recording(
    client: AsyncClient, admin: dict[str, str], sample_audio: Path
) -> None:
    """Parts of one meeting, handed over together.

    A recording split across three cards is one recording; asking for three
    transcripts and stitching them by hand is what this saves.
    """
    await client.post("/api/auth/login", json=admin)

    with sample_audio.open("rb") as first, sample_audio.open("rb") as second:
        response = await client.post(
            "/api/jobs",
            files=[
                ("file", ("part-one.wav", first, "audio/wav")),
                ("file", ("part-two.wav", second, "audio/wav")),
            ],
        )

    assert response.status_code == 201
    job = response.json()
    assert job["title"] == "part-one.wav +1"
    assert job["source_ref"] == "part-one.wav, part-two.wav"
