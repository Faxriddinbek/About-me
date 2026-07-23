"""Application factory and ASGI entry point.

``create_app`` assembles the FastAPI application: configuration, logging,
middleware, error handling, and routing. Keeping assembly in a factory makes it
trivial to build isolated app instances in tests with overridden settings.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger, request_id_ctxvar
from app.db.session import dispose_engine

logger = get_logger(__name__)

_REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown side effects.

    The database engine is created at import time; here we make sure its
    connection pool is disposed cleanly on shutdown so no connections leak.
    """
    settings = get_settings()
    logger.info(
        "Starting %s v%s (env=%s)",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.ENVIRONMENT,
    )
    yield
    await dispose_engine()
    logger.info("Shutdown complete; database engine disposed.")


def _configure_cors(app: FastAPI, settings: Settings) -> None:
    """Attach CORS middleware without ever pairing wildcard origins with credentials.

    Browsers reject ``Access-Control-Allow-Origin: *`` together with credentials,
    and allowing it would be insecure anyway, so credentials are enabled only
    when the configured origins are explicit.
    """
    origins = settings.cors_origins
    allow_all = not origins or "*" in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_app() -> FastAPI:
    """Build and return a fully configured FastAPI application."""
    settings = get_settings()
    configure_logging(settings)

    # Hide interactive docs and the schema in production to reduce surface area.
    docs_url = None if settings.is_prod else "/docs"
    redoc_url = None if settings.is_prod else "/redoc"
    openapi_url = None if settings.is_prod else "/openapi.json"

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    _configure_cors(app, settings)
    register_exception_handlers(app)

    @app.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Assign a request ID, time the request, and log its method/path/status."""
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = request_id_ctxvar.set(request_id)
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            status_code = response.status_code if response is not None else 500
            if response is not None:
                response.headers[_REQUEST_ID_HEADER] = request_id
            logger.info(
                "%s %s -> %s (%.2fms)",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_ctxvar.reset(token)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Liveness probe used by the frontend and uptime monitors."""
        return {"status": "ok", "version": settings.APP_VERSION}

    app.include_router(api_router, prefix="/api/v1")

    return app


# Module-level ASGI app so ``uvicorn app.main:app`` works out of the box.
app = create_app()
