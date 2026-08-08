"""Application factory.

`create_app()` is the single place that wires settings, logging, middleware,
and routers together. Keeping this assembly in one function (rather than
side effects scattered across modules) makes the app's startup behavior easy
to read top-to-bottom and easy to unit test in isolation via a fresh
instance per test.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.middleware.cors import add_cors_middleware
from app.middleware.request_logging import RequestLoggingMiddleware

logger = get_logger(__name__)


def _make_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "%s v%s starting in %s mode",
            settings.APP_NAME,
            settings.APP_VERSION,
            settings.ENVIRONMENT,
        )
        yield
        logger.info("%s shutting down", settings.APP_NAME)

    return lifespan


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=_make_lifespan(settings),
    )

    add_cors_middleware(app, settings)
    app.add_middleware(RequestLoggingMiddleware)

    # Single include point: `api_router` aggregates root, health, and every
    # versioned API — see app/api/router.py.
    app.include_router(api_router)

    return app


app = create_app()
