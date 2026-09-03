from pathlib import Path

from httpx import AsyncClient

from app.config import Settings
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import SttStub
from tests.test_exports import transcribed
from tests.test_url_ingest import settings_with_stt

MARIA = {"username": "maria", "password": "a longer password"}


async def as_admin(client: AsyncClient, admin: dict[str, str]) -> None:
    await client.post("/api/auth/login", json=admin)


async def test_an_account_an_admin_creates_can_sign_in(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await as_admin(client, ADMIN_CREDENTIALS)
        created = await client.post("/api/users", json=MARIA)

        # A separate client: her own cookie jar, nothing borrowed.
        async with running_client(settings) as hers:
            signed_in = await hers.post("/api/auth/login", json=MARIA)

    assert created.status_code == 201
    assert created.json()["is_admin"] is False
    assert signed_in.status_code == 200
    assert signed_in.json()["username"] == "maria"


async def test_a_new_account_is_nobody_special(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await as_admin(client, ADMIN_CREDENTIALS)
        await client.post("/api/users", json=MARIA)

        async with running_client(settings) as hers:
            await hers.post("/api/auth/login", json=MARIA)
            refused = await hers.get("/api/users")

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "admin_required"


async def test_the_list_says_what_each_person_holds(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        await transcribed(client, sample_audio, SttStub(), settings)
        await client.post("/api/users", json=MARIA)

        listed = (await client.get("/api/users")).json()

    holdings = {row["username"]: row["jobs"] for row in listed}
    assert holdings == {"admin": 1, "maria": 0}


async def test_somebody_with_recordings_is_not_deleted_by_accident(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Deleting gigabytes of somebody's audio should take more than one click."""
    settings = settings_with_stt(tmp_path)

    async with running_client(settings) as client:
        job = await transcribed(client, sample_audio, SttStub(), settings)
        await client.post("/api/users", json=MARIA)
        listed = (await client.get("/api/users")).json()
        maria = next(row for row in listed if row["username"] == "maria")

        # Hers now, so the admin is not deleting himself.
        async with running_client(settings) as hers:
            await hers.post("/api/auth/login", json=MARIA)
            with sample_audio.open("rb") as handle:
                await hers.post("/api/jobs", files={"file": ("hers.wav", handle, "audio/wav")})

        refused = await client.delete(f"/api/users/{maria['id']}")
        removed = await client.delete(f"/api/users/{maria['id']}", params={"with_jobs": True})
        left = (await client.get("/api/users")).json()

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "user_has_jobs"
    assert refused.json()["error"]["params"] == {"jobs": 1}
    assert removed.status_code == 204
    assert [row["username"] for row in left] == ["admin"]
    # The admin's own recording is untouched.
    assert (settings.media_dir / job["id"]).is_dir()


async def test_the_last_administrator_stays_one(tmp_path: Path) -> None:
    """Otherwise the instance locks itself from the outside."""
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await as_admin(client, ADMIN_CREDENTIALS)
        me = (await client.get("/api/auth/me")).json()

        demoted = await client.patch(f"/api/users/{me['id']}", json={"is_admin": False})

    assert demoted.status_code == 409
    assert demoted.json()["error"]["code"] == "last_admin"


async def test_nobody_deletes_themselves(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await as_admin(client, ADMIN_CREDENTIALS)
        me = (await client.get("/api/auth/me")).json()

        refused = await client.delete(f"/api/users/{me['id']}")

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "cannot_delete_self"


async def test_a_password_is_changed_by_the_person_who_knows_it(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    changed = {**ADMIN_CREDENTIALS, "password": "an entirely new password"}

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await as_admin(client, ADMIN_CREDENTIALS)

        accepted = await client.post(
            "/api/auth/password",
            json={
                "current_password": ADMIN_CREDENTIALS["password"],
                "new_password": changed["password"],
            },
        )

        async with running_client(settings) as again:
            with_old = await again.post("/api/auth/login", json=ADMIN_CREDENTIALS)
            with_new = await again.post("/api/auth/login", json=changed)

    assert accepted.status_code == 204
    assert with_old.status_code == 401
    assert with_new.status_code == 200


async def test_the_wrong_current_password_changes_nothing(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await as_admin(client, ADMIN_CREDENTIALS)

        refused = await client.post(
            "/api/auth/password",
            json={"current_password": "not it at all", "new_password": "something else here"},
        )

        async with running_client(settings) as again:
            still_works = await again.post("/api/auth/login", json=ADMIN_CREDENTIALS)

    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "invalid_credentials"
    assert still_works.status_code == 200


async def test_an_admin_can_hand_out_a_new_password(tmp_path: Path) -> None:
    """A forgotten password is the most ordinary reason to need an admin."""
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await as_admin(client, ADMIN_CREDENTIALS)
        maria = (await client.post("/api/users", json=MARIA)).json()

        await client.patch(f"/api/users/{maria['id']}", json={"password": "issued by the admin"})

        async with running_client(settings) as hers:
            signed_in = await hers.post(
                "/api/auth/login", json={"username": "maria", "password": "issued by the admin"}
            )

    assert signed_in.status_code == 200


async def test_accounts_are_not_managed_here_when_a_proxy_owns_them(tmp_path: Path) -> None:
    """There is no password to set: the identity belongs to the proxy."""
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", admin_users="alice", _env_file=None)
    alice = {"X-Remote-User": "alice"}

    async with running_client(settings) as client:
        listed = await client.get("/api/users", headers=alice)
        refused = await client.post("/api/users", json=MARIA, headers=alice)

    assert listed.status_code == 200
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "accounts_are_external"
