"""The API: `uvicorn --factory karaoke.api.app:create_app`. It never processes audio; it records jobs for the worker."""
from __future__ import annotations

import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from karaoke.api.preview import PreviewSource
from karaoke.api.realtime import Hub
from karaoke.api.routes import api, internal, sockets
from karaoke.api.search import CachedSearch, SearchFn, youtube_search
from karaoke.core.auth import CreationLimiter, HostSigner, LoginLimiter
from karaoke.core.config import Settings, load_settings
from karaoke.core.db import make_engine, make_sessionmaker, migrate, transaction
from karaoke.core.songs import expire_rooms

log = logging.getLogger("karaoke.api")


EXPIRY_CHECK_S = 60


async def close_expired(app: FastAPI) -> list[int]:
    """Rooms expire 24 h after they were made (docs/ARCHITECTURE.md, "Salas"): the expired ones close and their
    screens are told, as when a room is removed."""
    def expire() -> list[int]:
        with transaction(app.state.sessions) as session:
            return expire_rooms(session)

    closed = await run_in_threadpool(expire)
    if closed:
        log.info("salas expiradas: %s", closed)
        await app.state.hub.close_rooms(closed)
    return closed


async def expire_every_minute(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(EXPIRY_CHECK_S)
        try:
            await close_expired(app)
        except Exception:  # one bad minute must not stop the next ones
            log.exception("falha ao fechar salas expiradas")


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
        sweeper = asyncio.create_task(expire_every_minute(app))
        yield
        sweeper.cancel()
        engine.dispose()

    app = FastAPI(title="Karaokê", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessions = make_sessionmaker(engine)
    app.state.hub = Hub(app.state.sessions)
    app.state.host_signer = HostSigner()
    app.state.login_limiter = LoginLimiter()
    app.state.creation_limiter = CreationLimiter()
    app.state.search = CachedSearch(search)
    app.state.preview = preview or PreviewSource()
    app.include_router(api)
    app.include_router(internal)
    app.include_router(sockets)
    return app
