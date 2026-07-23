"""Domain exception hierarchy and FastAPI error handlers.

A small, explicit set of application errors lets the service and repository
layers signal failure semantically (for example ``NotFoundError``) instead of
leaking HTTP concerns downward. The handlers translate those errors — and any
unexpected exception — into one consistent JSON envelope, so the frontend always
parses errors the same way and stack traces never reach clients in production.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for all expected application errors.

    Carries an HTTP status, a stable machine-readable ``code`` (for the frontend
    to branch on), a human-readable ``message``, and optional structured
    ``detail``.
    """

    code: str = "app_error"
    message: str = "An application error occurred."
    http_status: int = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str | None = None,
        *,
        detail: Any | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.message
        self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "not_found"
    message = "The requested resource was not found."
    http_status = status.HTTP_404_NOT_FOUND


class ValidationError(AppError):
    code = "validation_error"
    message = "The request was invalid."
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY


class UnauthorizedError(AppError):
    code = "unauthorized"
    message = "Authentication is required or has failed."
    http_status = status.HTTP_401_UNAUTHORIZED


class RateLimitError(AppError):
    code = "rate_limited"
    message = "Too many requests. Please slow down."
    http_status = status.HTTP_429_TOO_MANY_REQUESTS


def _error_body(code: str, message: str, detail: Any | None) -> dict[str, Any]:
    """Build the canonical error envelope shared by every handler."""
    return {"error": {"code": code, "message": message, "detail": detail}}


def render_error(
    status_code: int, code: str, message: str, detail: Any | None = None
) -> JSONResponse:
    """Public helper to emit the standard error envelope.

    Exposed so infrastructure handlers registered outside this module (e.g. the
    slowapi rate-limit handler in ``main``) can reuse the exact same shape.
    """
    return JSONResponse(status_code=status_code, content=_error_body(code, message, detail))


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Translate a domain ``AppError`` (or subclass) into its JSON envelope."""
    return JSONResponse(
        status_code=exc.http_status,
        content=_error_body(exc.code, exc.message, exc.detail),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return request-validation failures in the same envelope as domain errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body(
            "validation_error",
            "The request failed validation.",
            exc.errors(),
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors.

    The full traceback is logged server-side for debugging, but the response
    body stays generic in production so internal details never leak to clients.
    """
    logger.exception("Unhandled exception during request")
    settings = get_settings()
    detail = str(exc) if settings.is_dev else None
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body(
            "internal_error",
            "An internal server error occurred.",
            detail,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register every error handler on the FastAPI application.

    Registering ``AppError`` covers all its subclasses because Starlette matches
    handlers by walking the exception's method-resolution order.
    """
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
