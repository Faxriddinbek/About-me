"""Shared pytest fixtures.

The test environment is forced to a dev, in-memory SQLite configuration *before*
any application module reads settings, so the suite is hermetic — fully isolated
from real configuration and requiring no external services. ``asyncio_mode =
auto`` (see ``pyproject.toml``) lets async tests run without per-test markers.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

# Configure the environment before importing anything that reads settings. An
# in-memory database keeps tests fast and free of on-disk side effects.
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

import httpx  # noqa: E402  — imported after the environment is configured
from httpx import ASGITransport  # noqa: E402

from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session")
def app() -> httpx.URL | object:
    """Build one application instance for the whole test session."""
    return create_app()


@pytest_asyncio.fixture
async def client(app: object) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client bound to the app in-process (no network, no live server)."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
