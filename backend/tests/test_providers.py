from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.config import Settings
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import LlmStub

STT = {"kind": "stt", "name": "Local whisper", "base_url": "http://whisper.test/v1"}
LLM = {"kind": "llm", "name": "Ollama", "base_url": "http://ollama.test/v1"}

# Long enough that masking cannot be mistaken for the key itself.
KEY = "sk-abcdefghijklmnopqrstuvwxyz0123456789"


async def as_admin(client: AsyncClient, admin: dict[str, str]) -> None:
    await client.post("/api/auth/login", json=admin)


async def test_a_provider_created_here_is_the_one_the_list_returns(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await as_admin(client, admin)

    created = await client.post("/api/providers", json={**STT, "default_model": "small"})
    listed = (await client.get("/api/providers")).json()

    assert created.status_code == 201
    assert [(row["name"], row["default_model"]) for row in listed] == [("Local whisper", "small")]


async def test_the_first_provider_of_a_kind_becomes_the_default(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    """Otherwise the only provider on the instance is still not the one used."""
    await as_admin(client, admin)

    created = await client.post("/api/providers", json=STT)

    assert created.json()["is_default"] is True


async def test_only_one_provider_of_a_kind_is_the_default(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await as_admin(client, admin)
    first = (await client.post("/api/providers", json=STT)).json()
    await client.post("/api/providers", json=LLM)

    second = await client.post(
        "/api/providers", json={**STT, "name": "Cloud whisper", "is_default": True}
    )
    listed = (await client.get("/api/providers")).json()

    assert second.json()["is_default"] is True
    defaults = {row["kind"]: row["name"] for row in listed if row["is_default"]}
    # The other kind is untouched: a new speech-to-text default says nothing
    # about which language model answers.
    assert defaults == {"stt": "Cloud whisper", "llm": "Ollama"}
    assert [row for row in listed if row["id"] == first["id"]][0]["is_default"] is False


async def test_the_key_is_never_returned_and_never_has_to_be_retyped(
    settings: Settings,
) -> None:
    """A key comes back masked, and an edit that does not mention it keeps it.

    Proved where it matters rather than by comparing masks: the probe sends the
    stored key to the endpoint, so the stub sees whether the real one survived.
    """
    stub = LlmStub()

    async with running_client(settings, probe_client_factory=probe_via(stub)) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await as_admin(client, ADMIN_CREDENTIALS)

        created = (await client.post("/api/providers", json={**LLM, "api_key": KEY})).json()
        renamed = await client.patch(
            f"/api/providers/{created['id']}", json={"name": "Renamed"}
        )
        await client.post("/api/providers/test", json={"provider_id": created["id"]})

    assert created["api_key"] == "sk-…6789"
    assert renamed.json()["name"] == "Renamed"
    assert stub.authorizations == [f"Bearer {KEY}"]


async def test_an_empty_key_clears_it(client: AsyncClient, admin: dict[str, str]) -> None:
    await as_admin(client, admin)
    created = (await client.post("/api/providers", json={**LLM, "api_key": KEY})).json()

    cleared = await client.patch(f"/api/providers/{created['id']}", json={"api_key": ""})

    assert cleared.json()["api_key"] is None


async def test_deleting_a_provider_returns_its_presets_to_the_default(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await as_admin(client, admin)
    provider = (await client.post("/api/providers", json=LLM)).json()
    spare = (await client.post("/api/providers", json={**LLM, "name": "Spare"})).json()
    preset = (
        await client.post(
            "/api/presets",
            json={
                "name": "Bullets",
                "description": None,
                "system_prompt": "Be brief.",
                "user_template": "{transcript}",
                "model_override": None,
                "provider_id": provider["id"],
                "temperature": 0.3,
                "output_format": "markdown",
            },
        )
    ).json()

    removed = await client.delete(f"/api/providers/{provider['id']}")
    presets = (await client.get("/api/presets")).json()

    assert removed.status_code == 204
    assert spare["id"] != provider["id"]
    assert [row["provider_id"] for row in presets if row["id"] == preset["id"]] == [None]


async def test_the_last_speech_to_text_provider_cannot_be_deleted(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    """One click should not be able to make the instance unable to transcribe."""
    await as_admin(client, admin)
    only = (await client.post("/api/providers", json=STT)).json()

    refused = await client.delete(f"/api/providers/{only['id']}")

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "last_stt_provider"


async def test_a_spare_speech_to_text_provider_can_be_deleted(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await as_admin(client, admin)
    await client.post("/api/providers", json=STT)
    spare = (await client.post("/api/providers", json={**STT, "name": "Cloud"})).json()

    removed = await client.delete(f"/api/providers/{spare['id']}")

    assert removed.status_code == 204
    assert [row["name"] for row in (await client.get("/api/providers")).json()] == ["Local whisper"]


async def test_deleting_the_default_hands_the_job_to_whoever_is_left(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await as_admin(client, admin)
    first = (await client.post("/api/providers", json=STT)).json()
    await client.post("/api/providers", json={**STT, "name": "Cloud"})

    await client.delete(f"/api/providers/{first['id']}")
    listed = (await client.get("/api/providers")).json()

    assert first["is_default"] is True
    assert [(row["name"], row["is_default"]) for row in listed] == [("Cloud", True)]


async def test_a_reader_may_look_at_providers_but_not_change_them(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", _env_file=None)
    reader = {"X-Remote-User": "alice"}

    async with running_client(settings) as client:
        listed = await client.get("/api/providers", headers=reader)
        refused = await client.post("/api/providers", json=STT, headers=reader)

    assert listed.status_code == 200
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "admin_required"


async def test_the_environment_can_name_an_administrator(tmp_path: Path) -> None:
    """Behind a proxy nobody is an admin, so an instance would be unconfigurable."""
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", admin_users="bob,alice", _env_file=None)
    alice = {"X-Remote-User": "alice"}

    async with running_client(settings) as client:
        created = await client.post("/api/providers", json=STT, headers=alice)
        me = await client.get("/api/auth/me", headers=alice)

    assert created.status_code == 201
    assert me.json()["is_admin"] is True


async def test_the_probe_reports_what_the_endpoint_offers(settings: Settings) -> None:
    stub = LlmStub(models=["llama3.1", "qwen2.5"])

    async with running_client(settings, probe_client_factory=probe_via(stub)) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await as_admin(client, ADMIN_CREDENTIALS)

        probed = await client.post(
            "/api/providers/test", json={"base_url": "http://ollama.test/v1"}
        )

    assert probed.status_code == 200
    assert probed.json()["reachable"] is True
    assert probed.json()["models"] == ["llama3.1", "qwen2.5"]


async def test_a_probe_that_finds_nobody_home_is_an_answer_not_a_failure(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    """Pressing "test" and being told nothing answered is a successful test."""
    await as_admin(client, admin)

    # Port 9 is the discard service: nothing listens, and the refusal is instant.
    probed = await client.post("/api/providers/test", json={"base_url": "http://127.0.0.1:9/v1"})

    assert probed.status_code == 200
    assert probed.json()["reachable"] is False
    assert probed.json()["error_code"] == "provider_unreachable"


def probe_via(stub: LlmStub):  # type: ignore[no-untyped-def]
    """Point the probe at a stub server without letting it near the network."""

    def factory(base_url: str, api_key: str | None) -> AsyncClient:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        return AsyncClient(
            transport=ASGITransport(app=stub.app), base_url=base_url, headers=headers
        )

    return factory
