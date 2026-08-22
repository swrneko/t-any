import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

ADMIN_CREDENTIALS = {"username": "admin", "password": "correct horse battery staple"}


@asynccontextmanager
async def running_client(
    settings: Settings, probe_client_factory: object | None = None
) -> AsyncIterator[AsyncClient]:
    """Start the app for real -- lifespan included, so migrations actually run."""
    application = create_app(settings)
    if probe_client_factory is not None:
        # The one place the API itself dials out. A stub server rather than a
        # patch, so the request is really made and really parsed.
        application.state.probe_client_factory = probe_client_factory
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, auth_mode="builtin", _env_file=None)


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    async with running_client(settings) as ac:
        yield ac


@pytest.fixture(scope="session")
def sample_audio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Three seconds of a 440 Hz tone, produced by the same ffmpeg the app uses.

    Generating it beats committing a binary: the fixture proves ffmpeg is
    present and exercises the real command line, which is where the bugs are.
    """
    path = tmp_path_factory.mktemp("fixtures") / "sample.wav"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-y", str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
async def admin(client: AsyncClient) -> dict[str, str]:
    """An installation that has already been through the setup wizard."""
    response = await client.post("/api/setup", json=ADMIN_CREDENTIALS)
    assert response.status_code == 201
    return ADMIN_CREDENTIALS
