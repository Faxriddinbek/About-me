"""Structured application logging.

JSON logs in production make output machine-parseable for log aggregators;
human-readable logs in development keep the console legible. Every record is
stamped with the current request's ID via a ``ContextVar`` so log lines can be
correlated across a single request without threading the ID through every call.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from app.core.config import Settings

# Holds the active request ID for the duration of a request. Defaults to "-" so
# records emitted outside any request (startup, shutdown) still carry the field.
request_id_ctxvar: ContextVar[str] = ContextVar("request_id", default="-")

# Extra ``LogRecord`` attributes promoted into structured output when present.
_REQUEST_FIELDS = ("method", "path", "status_code", "duration_ms")


class RequestIdFilter(logging.Filter):
    """Inject the current request ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctxvar.get()
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for field in _REQUEST_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    """Readable console formatter that still surfaces the request ID."""

    _FMT = "%(asctime)s | %(levelname)-8s | %(name)s | [%(request_id)s] | %(message)s"

    def __init__(self) -> None:
        super().__init__(fmt=self._FMT, datefmt="%Y-%m-%d %H:%M:%S")


def configure_logging(settings: Settings) -> None:
    """Configure the root logger's handler and formatter for the environment.

    Called once at startup, before the app serves traffic, so all subsequent
    output — including from third-party libraries — follows the same format and
    carries a request ID.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonFormatter() if settings.is_prod else HumanFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # Route uvicorn's loggers through our handler so access/error logs share the
    # same format and request-ID stamping instead of printing their own way.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger; a thin wrapper for a single, consistent entry point."""
    return logging.getLogger(name)
