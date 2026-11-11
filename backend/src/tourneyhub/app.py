import logging
import logging.config
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid7

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from tourneyhub.api import admin, auth, leagues, me, players, public, tournaments
from tourneyhub.api.errors import install_error_handlers
from tourneyhub.api.schemas import ErrorResponse
from tourneyhub.db.session import create_db_engine, create_session_factory
from tourneyhub.logging_config import LOGGING_CONFIG, request_id
from tourneyhub.settings import Settings

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
_PUBLIC_PATH = API_PREFIX + public.PUBLIC_PREFIX


class _RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            # Not reset: uvicorn logs an unhandled exception after this returns (§4.6).
            request_id.set(uuid7().hex)
        await self.app(scope, receive, send)


class _PublicHeadersMiddleware:
    """Headers for every answer under /api/v1/public, errors included (ADR-005).

    The path carries the share token: no cache may keep the answer, and no
    request from it names the address (FR-071).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if path != _PUBLIC_PATH and not path.startswith(_PUBLIC_PATH + "/"):
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["Referrer-Policy"] = "no-referrer"
            await send(message)

        await self.app(scope, receive, send_with_headers)


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
    app.add_middleware(_PublicHeadersMiddleware)
    app.add_middleware(_RequestIdMiddleware)
    install_error_handlers(app)
    for router in (
        admin.router,
        auth.router,
        leagues.router,
        me.router,
        players.router,
        public.router,
        tournaments.router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    logger.info("application created", extra={"env": settings.env})
    return app
