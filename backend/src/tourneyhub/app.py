import logging
import logging.config
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid7

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send

from tourneyhub.api import auth, leagues, me, players, tournaments
from tourneyhub.api.errors import install_error_handlers
from tourneyhub.api.schemas import ErrorResponse
from tourneyhub.db.session import create_db_engine, create_session_factory
from tourneyhub.logging_config import LOGGING_CONFIG, request_id
from tourneyhub.settings import Settings

logger = logging.getLogger(__name__)


class _RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            # Not reset: uvicorn logs an unhandled exception after this returns (§4.6).
            request_id.set(uuid7().hex)
        await self.app(scope, receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application; a missing or invalid setting stops startup."""
    logging.config.dictConfig(LOGGING_CONFIG)
    settings = settings or Settings()
    engine = create_db_engine(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        lifespan=lifespan,
        generate_unique_id_function=lambda route: route.name,
        responses={HTTPStatus.UNPROCESSABLE_CONTENT: {"model": ErrorResponse}},
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.add_middleware(_RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(leagues.router, prefix="/api/v1")
    app.include_router(me.router, prefix="/api/v1")
    app.include_router(players.router, prefix="/api/v1")
    app.include_router(tournaments.router, prefix="/api/v1")
    logger.info("application created", extra={"env": settings.env})
    return app
