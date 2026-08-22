import asyncio
from pathlib import Path

from app.config import Settings
from tests.conftest import running_client


async def test_disabled_auth_serves_every_request_as_the_local_user(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_mode="disabled", _env_file=None)

    async with running_client(settings) as client:
        me = await client.get("/api/auth/me")

        assert me.status_code == 200
        assert me.json()["is_admin"] is True


async def test_simultaneous_first_requests_resolve_to_one_user(tmp_path: Path) -> None:
    """Every browser tab hits the API at once on first load."""
    settings = Settings(data_dir=tmp_path, auth_mode="disabled", _env_file=None)

    async with running_client(settings) as client:
        responses = await asyncio.gather(*(client.get("/api/auth/me") for _ in range(6)))

        assert [response.status_code for response in responses] == [200] * 6
        assert len({response.json()["id"] for response in responses}) == 1


async def test_disabled_auth_skips_the_setup_wizard(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_mode="disabled", _env_file=None)

    async with running_client(settings) as client:
        status = await client.get("/api/setup/status")

        assert status.json() == {
            "needs_setup": False,
            "auth_mode": "disabled",
            "has_diarizer": False,
        }


async def test_proxy_auth_trusts_the_identity_header(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", _env_file=None)

    async with running_client(settings) as client:
        me = await client.get("/api/auth/me", headers={"X-Remote-User": "marina"})

        assert me.status_code == 200
        assert me.json()["username"] == "marina"


async def test_proxy_auth_rejects_a_request_without_the_identity_header(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", _env_file=None)

    async with running_client(settings) as client:
        me = await client.get("/api/auth/me")

        assert me.status_code == 401
        assert me.json()["error"]["code"] == "not_authenticated"
