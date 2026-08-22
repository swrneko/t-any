from pathlib import Path

from httpx import AsyncClient

from app.config import Settings
from tests.conftest import running_client
from tests.stubs import SttStub
from tests.test_exports import transcribed
from tests.test_url_ingest import run_worker_once, settings_with_stt


async def another(client: AsyncClient, audio: Path, settings: Settings, name: str) -> dict:  # type: ignore[type-arg]
    with audio.open("rb") as handle:
        job = (await client.post("/api/jobs", files={"file": (name, handle, "audio/wav")})).json()
    await run_worker_once(settings, SttStub())
    return job


async def test_a_deleted_recording_leaves_nothing_behind(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)

        removed = await client.delete(f"/api/jobs/{job['id']}")
        listed = await client.get("/api/jobs")
        gone = await client.get(f"/api/jobs/{job['id']}")
        # The index has to follow: a recording that still answers searches was
        # not deleted, it was hidden.
        found = await client.get("/api/search", params={"q": "Kenobi"})

    assert removed.status_code == 204
    assert listed.json() == []
    assert gone.status_code == 404
    assert found.json() == []
    assert not (settings.media_dir / job["id"]).exists()


async def test_the_list_says_what_a_recording_takes(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await transcribed(client, sample_audio, SttStub(), settings)

        listed = (await client.get("/api/jobs")).json()

    assert listed[0]["audio_bytes"] > 0


async def test_dropping_the_audio_keeps_the_words(tmp_path: Path, sample_audio: Path) -> None:
    """The expensive half and the valuable half are not the same half."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)

        dropped = await client.delete(f"/api/jobs/{job['id']}/audio")
        transcript = await client.get(f"/api/jobs/{job['id']}/transcript")
        audio = await client.get(f"/api/jobs/{job['id']}/audio")
        listed = (await client.get("/api/jobs")).json()

    assert dropped.status_code == 204
    assert [segment["text"] for segment in transcript.json()["segments"]] == [
        "Hello there.",
        "General Kenobi.",
    ]
    assert audio.status_code == 404
    assert listed[0]["audio_bytes"] is None


async def test_a_recording_still_being_worked_on_is_not_deleted(
    client: AsyncClient, admin: dict[str, str], sample_audio: Path
) -> None:
    """Otherwise the worker writes into a directory that was just removed."""
    await client.post("/api/auth/login", json=admin)
    with sample_audio.open("rb") as handle:
        job = (
            await client.post("/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")})
        ).json()

    refused = await client.delete(f"/api/jobs/{job['id']}")

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "job_not_finished"


async def test_one_persons_recording_is_not_anothers_to_delete(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", _env_file=None)

    async with running_client(settings) as client:
        with sample_audio.open("rb") as handle:
            job = (
                await client.post(
                    "/api/jobs",
                    files={"file": ("meeting.wav", handle, "audio/wav")},
                    headers={"X-Remote-User": "alice"},
                )
            ).json()

        refused = await client.delete(
            f"/api/jobs/{job['id']}", headers={"X-Remote-User": "bob"}
        )

    assert refused.status_code == 404


async def test_several_recordings_go_at_once(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        first = await transcribed(client, sample_audio, SttStub(), settings)
        second = await another(client, sample_audio, settings, "second.wav")
        third = await another(client, sample_audio, settings, "third.wav")

        removed = await client.post(
            "/api/jobs/delete", json={"ids": [first["id"], second["id"]]}
        )
        listed = (await client.get("/api/jobs")).json()

    assert removed.json() == {"deleted": 2, "skipped": 0}
    assert [row["id"] for row in listed] == [third["id"]]
    assert not (settings.media_dir / first["id"]).exists()


async def test_several_recordings_can_lose_their_audio_at_once(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        first = await transcribed(client, sample_audio, SttStub(), settings)
        second = await another(client, sample_audio, settings, "second.wav")

        freed = await client.post(
            "/api/jobs/delete", json={"ids": [first["id"], second["id"]], "audio_only": True}
        )
        listed = (await client.get("/api/jobs")).json()

    assert freed.json() == {"deleted": 2, "skipped": 0}
    assert [row["audio_bytes"] for row in listed] == [None, None]
    assert {row["status"] for row in listed} == {"done"}


async def test_a_link_to_a_deleted_recording_stops_working(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)
        share = (
            await client.post(f"/api/jobs/{job['id']}/share", json={"expires_in_days": None})
        ).json()

        await client.delete(f"/api/jobs/{job['id']}")
        visited = await client.get(f"/api/public/shares/{share['token']}")

    assert visited.status_code == 404
    assert visited.json()["error"]["code"] == "share_not_found"
