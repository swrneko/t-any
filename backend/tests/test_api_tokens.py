from pathlib import Path

from httpx import AsyncClient

from app.config import Settings
from tests.conftest import ADMIN_CREDENTIALS, running_client


async def issue(client: AsyncClient, name: str = "my scripts") -> dict:  # type: ignore[type-arg]
    await client.post("/api/setup", json=ADMIN_CREDENTIALS)
    await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
    return (await client.post("/api/tokens", json={"name": name})).json()


async def test_a_token_is_shown_once_and_never_again(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await client.post("/api/auth/login", json=admin)

    created = (await client.post("/api/tokens", json={"name": "my scripts"})).json()
    listed = (await client.get("/api/tokens")).json()

    assert created["token"].startswith("tany_")
    assert listed[0]["name"] == "my scripts"
    assert "token" not in listed[0]


async def test_a_token_works_where_a_session_would(tmp_path: Path, sample_audio: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        token = (await issue(client))["token"]

        # A different client: no cookie jar, nothing but the header.
        async with running_client(settings) as script:
            headers = {"Authorization": f"Bearer {token}"}
            with sample_audio.open("rb") as handle:
                created = await script.post(
                    "/api/jobs",
                    files={"file": ("meeting.wav", handle, "audio/wav")},
                    headers=headers,
                )
            listed = await script.get("/api/jobs", headers=headers)

        assert created.status_code == 201
        assert [job["id"] for job in listed.json()] == [created.json()["id"]]


async def test_a_token_belongs_to_the_person_who_made_it(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        token = (await issue(client))["token"]
        with sample_audio.open("rb") as handle:
            job = (
                await client.post("/api/jobs", files={"file": ("meeting.wav", handle, "audio/wav")})
            ).json()

        async with running_client(settings) as script:
            response = await script.get(
                f"/api/jobs/{job['id']}", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 200


async def test_a_made_up_token_is_refused(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        await issue(client)

        async with running_client(settings) as script:
            response = await script.get(
                "/api/jobs", headers={"Authorization": "Bearer tany_not-a-real-token"}
            )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"


async def test_revoking_a_token_stops_it_immediately(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        created = await issue(client)
        headers = {"Authorization": f"Bearer {created['token']}"}

        assert (await client.delete(f"/api/tokens/{created['id']}")).status_code == 204

        async with running_client(settings) as script:
            assert (await script.get("/api/jobs", headers=headers)).status_code == 401


async def test_using_a_token_records_when_it_was_last_seen(tmp_path: Path) -> None:
    """The only way to answer "is this old key still in use?" before deleting it."""
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        created = await issue(client)
        assert (await client.get("/api/tokens")).json()[0]["last_used_at"] is None

        async with running_client(settings) as script:
            await script.get("/api/jobs", headers={"Authorization": f"Bearer {created['token']}"})

        assert (await client.get("/api/tokens")).json()[0]["last_used_at"] is not None


async def test_tokens_need_a_session_to_manage(client: AsyncClient, admin: dict[str, str]) -> None:
    """A token must not be able to mint another token: a leaked one would then
    outlive its own revocation."""
    await client.post("/api/auth/login", json=admin)
    token = (await client.post("/api/tokens", json={"name": "my scripts"})).json()["token"]

    response = await client.post(
        "/api/tokens", json={"name": "another"}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "session_required"
