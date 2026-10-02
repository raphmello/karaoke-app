"""The API: `uvicorn --factory karaoke.api.app:create_app`. It never processes audio; it records jobs for the worker."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from karaoke.api.preview import PreviewSource
from karaoke.api.realtime import Hub
from karaoke.api.routes import api, internal, sockets
from karaoke.api.search import CachedSearch, SearchFn, youtube_search
from karaoke.core.auth import HostSigner, LoginLimiter
from karaoke.core.config import Settings, load_settings
from karaoke.core.db import make_engine, make_sessionmaker, migrate

log = logging.getLogger("karaoke.api")


def create_app(
    settings: Settings | None = None, search: SearchFn = youtube_search, preview: PreviewSource | None = None
) -> FastAPI:
    # uvicorn configures only its own loggers; this shows the app's (worker events, rooms opened)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("alembic").setLevel(logging.WARNING)
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        migrate(engine)
        if not settings.host_pin:
            log.warning("HOST_PIN não definido no .env: ninguém consegue entrar como host")
        yield
        engine.dispose()

    app = FastAPI(title="Karaokê", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessions = make_sessionmaker(engine)
    app.state.hub = Hub(app.state.sessions)
    app.state.host_signer = HostSigner()
    app.state.login_limiter = LoginLimiter()
    app.state.search = CachedSearch(search)
    app.state.preview = preview or PreviewSource()
    app.include_router(api)
    app.include_router(internal)
    app.include_router(sockets)
    return app
