import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    auth,
    health,
    jobs,
    presets,
    providers,
    public,
    search,
    setup,
    summaries,
    tokens,
)
# Aliased: `settings` is the name of the configuration object everywhere else
# in this module, and the router must not shadow it.
from app.api import settings as settings_api
from app.config import Settings
from app.db import Database
from app.errors import register_error_handlers
from app.migrator import upgrade_to_head
from app.secrets import load_or_create_secret
from app.seed import seed_builtin_presets, seed_providers
from app.sessions import SessionSigner
from app.static import mount_frontend, mount_share_preview


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    settings.ensure_dirs()
    # Migrations run automatically: "exec into the container and upgrade" is a guaranteed bug report
    await asyncio.to_thread(upgrade_to_head, settings.db_path)
    app.state.db = Database(settings.db_path)
    app.state.secret = load_or_create_secret(settings.secret_key_path)
    app.state.sessions = SessionSigner(app.state.secret, settings.session_max_age_days)

    async with app.state.db.session_factory() as session:
        await seed_providers(session, settings, app.state.secret)
        await seed_builtin_presets(session)

    try:
        yield
    finally:
        await app.state.db.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="transcribe-anything", lifespan=lifespan)
    app.state.settings = settings or Settings()
    register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(setup.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(providers.router, prefix="/api")
    app.include_router(presets.router, prefix="/api")
    app.include_router(summaries.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(public.router, prefix="/api")
    app.include_router(tokens.router, prefix="/api")
    app.include_router(settings_api.router, prefix="/api")
    mount_share_preview(app, app.state.settings.frontend_dist)
    mount_frontend(app, app.state.settings.frontend_dist)
    return app
