"""Shared pytest fixtures.

Integration tests run against a real (in-memory) SQLite database shared across
the whole test via a ``StaticPool`` single connection, with the app's
``get_session`` dependency overridden to use it. The environment is forced to a
dev configuration — with a known admin token and ``TRUST_PROXY`` on so tests can
set the client IP via ``X-Forwarded-For`` — before any app module reads settings.
``asyncio_mode = auto`` (pyproject.toml) lets async tests/fixtures run without
per-item markers.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

# Configure the environment before importing anything that reads settings.
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TRUST_PROXY", "true")
# A throwaway directory, so uploads in tests never touch the working tree.
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="portfolio-uploads-"))

import httpx  # noqa: E402  — imported after the environment is configured
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402, F401  — registers models on Base.metadata
from app.db.base import Base  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.main import create_app  # noqa: E402

TEST_ADMIN_TOKEN = "test-admin-token"
ADMIN_HEADERS = {"X-Admin-Token": TEST_ADMIN_TOKEN}


def make_image(
    width: int = 800,
    height: int = 600,
    *,
    fmt: str = "JPEG",
    mode: str = "RGB",
    exif: Any | None = None,
) -> bytes:
    """Encode a real test image.

    Uploads are decoded and re-encoded, so tests cannot hand the API a
    hand-written byte string and call it a photo.
    """
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    fill = "red" if mode == "RGB" else (255, 0, 0, 128)
    image = Image.new(mode, (width, height), fill)
    if exif is not None:
        image.save(buffer, fmt, exif=exif)
    else:
        image.save(buffer, fmt)
    return buffer.getvalue()


def upload_files(name: str, data: bytes, content_type: str = "image/jpeg") -> dict:
    """The multipart payload shape the upload endpoint expects."""
    return {"file": (name, data, content_type)}


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[Any]:
    """A fresh in-memory database per test, on one shared connection.

    ``StaticPool`` keeps a single connection so every session in the test sees
    the same in-memory schema and data (otherwise each connection would get its
    own empty database).
    """
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: Any) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """Clear slowapi's process-global counters so limits don't leak between tests."""
    from app.api.limiter import limiter

    storage = getattr(limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client bound to a fresh app whose DB session uses the test engine."""
    application = create_app()

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seed(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[None]]:
    """Return an async helper that persists ORM model instances for a test."""

    async def _seed(*objects: Any) -> None:
        async with session_factory() as session:
            session.add_all(objects)
            await session.commit()

    return _seed
