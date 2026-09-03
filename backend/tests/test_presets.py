from pathlib import Path

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.presets import BUILTIN_PRESETS, BuiltinPreset
from tests.conftest import running_client

CUSTOM = {
    "name": "For my Obsidian vault",
    "description": "Bullets only, nothing else",
    "system_prompt": "You write terse bullet points.",
    "user_template": "Summarise:\n\n{transcript}",
    "temperature": 0.2,
    "output_format": "markdown",
}


async def test_the_builtin_presets_are_there_from_the_start(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    """Being able to invent a preset is the reason to host this yourself, but
    the first run still has to be useful without inventing anything."""
    await client.post("/api/auth/login", json=admin)

    presets = (await client.get("/api/presets")).json()

    assert len(presets) >= 5
    assert all(preset["is_builtin"] for preset in presets)
    # Names are shown to the user, so they are translated in the UI from a
    # stable key rather than served pre-translated from the database.
    assert all(preset["builtin_key"] for preset in presets)
    assert "{transcript}" in presets[0]["user_template"]


async def test_the_builtins_offer_both_ways_of_being_brief(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    """A summary and a retelling are not the same request.

    "What was this about" is answered in a few sentences that judge; "tell me
    what was said" follows the thing from beginning to end and judges nothing.
    Asking one prompt for both gets a verdict where a reader wanted the story.
    """
    await client.post("/api/auth/login", json=admin)

    presets = {preset["builtin_key"]: preset for preset in (await client.get("/api/presets")).json()}

    assert "brief" in presets and "retelling" in presets
    assert presets["brief"]["user_template"] != presets["retelling"]["user_template"]
    assert all("{transcript}" in preset["user_template"] for preset in presets.values())


async def test_a_custom_preset_can_be_created_and_changed(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await client.post("/api/auth/login", json=admin)

    created = await client.post("/api/presets", json=CUSTOM)
    assert created.status_code == 201
    preset = created.json()
    assert preset["name"] == CUSTOM["name"]
    assert preset["is_builtin"] is False

    updated = await client.put(f"/api/presets/{preset['id']}", json=CUSTOM | {"name": "Renamed"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"

    assert "Renamed" in (await client.get("/api/presets")).text


async def test_a_preset_must_keep_the_transcript_placeholder(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    """Without it the model is asked to summarise nothing at all, and answers
    anyway."""
    await client.post("/api/auth/login", json=admin)

    refused = await client.post(
        "/api/presets", json=CUSTOM | {"user_template": "Summarise the meeting."}
    )

    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "template_without_transcript"


async def test_a_builtin_preset_cannot_be_edited_or_deleted(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await client.post("/api/auth/login", json=admin)
    builtin = (await client.get("/api/presets")).json()[0]

    edited = await client.put(f"/api/presets/{builtin['id']}", json=CUSTOM)
    removed = await client.delete(f"/api/presets/{builtin['id']}")

    assert edited.status_code == 409
    assert edited.json()["error"]["code"] == "preset_is_builtin"
    assert removed.status_code == 409


async def test_a_custom_preset_can_be_deleted(
    client: AsyncClient, admin: dict[str, str]
) -> None:
    await client.post("/api/auth/login", json=admin)
    preset = (await client.post("/api/presets", json=CUSTOM)).json()

    assert (await client.delete(f"/api/presets/{preset['id']}")).status_code == 204
    assert CUSTOM["name"] not in (await client.get("/api/presets")).text


async def test_a_builtin_added_later_arrives_on_an_installation_that_already_ran(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding a preset to a release must not mean a fresh database.

    The seeder matches on the key rather than counting rows, so an instance
    that has been running since before the preset existed picks it up on the
    next start -- and the ones already there are not inserted a second time.
    """
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", _env_file=None)
    header = {"X-Remote-User": "marina"}

    async with running_client(settings) as client:
        before = (await client.get("/api/presets", headers=header)).json()

    # Inserted in the middle of the catalogue rather than at the end, which is
    # where a preset that belongs beside an older one really goes.
    added = BuiltinPreset(
        key="afterwards",
        name="Added in a later release",
        description="",
        system_prompt="You are careful.",
        user_template="{transcript}",
        temperature=0.2,
    )
    later = BUILTIN_PRESETS[:1] + (added,) + BUILTIN_PRESETS[1:]
    monkeypatch.setattr("app.presets.BUILTIN_PRESETS", later)
    monkeypatch.setattr("app.seed.BUILTIN_PRESETS", later)

    async with running_client(settings) as client:
        after = (await client.get("/api/presets", headers=header)).json()

    keys = [preset["builtin_key"] for preset in after]
    assert len(after) == len(before) + 1
    assert keys.count("brief") == 1
    # Where a preset stands in the list is the catalogue's business, not a
    # record of what day each row happened to be written: two installations of
    # the same release must offer the same list in the same order, however long
    # each of them has been running.
    assert keys == [preset.key for preset in later]


async def test_someone_elses_preset_is_invisible(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, auth_mode="proxy", _env_file=None)

    async with running_client(settings) as client:
        await client.post("/api/presets", json=CUSTOM, headers={"X-Remote-User": "marina"})

        stranger = await client.get("/api/presets", headers={"X-Remote-User": "pavel"})

        names = [preset["name"] for preset in stranger.json()]
        assert CUSTOM["name"] not in names
        assert names, "the builtins belong to everyone"
