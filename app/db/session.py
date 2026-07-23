"""Async database engine and session lifecycle.

The engine and sessionmaker are created once and shared across the app.
``get_session`` is the FastAPI dependency every route and service uses to obtain
a transactional ``AsyncSession`` that commits on success and rolls back on
error — keeping transaction handling in one place instead of scattered across
the codebase.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    future=True,
)

# ``expire_on_commit=False`` keeps ORM objects usable after commit; under async
# a lazy post-commit refresh would trigger unexpected (and forbidden) I/O.
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional session, committing on success, rolling back on error."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine's connection pool. Called during application shutdown."""
    await engine.dispose()
