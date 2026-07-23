"""Alembic environment configured for an async SQLAlchemy engine.

The database URL is read from the application settings rather than
``alembic.ini`` so the DSN (and its secrets) live in one place. Migrations run
through an async engine — the online path builds an ``AsyncEngine`` and drives
the synchronous migration routines via ``connection.run_sync``.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import get_settings
from app.db.base import Base

# Importing the models package registers every model on ``Base.metadata`` so
# autogenerate can see the full schema.
import app.models  # noqa: F401  (imported for its registration side effect)

# Alembic Config object, providing access to values in the .ini file.
config = context.config

# Inject the async database URL from application settings. Set on the config so
# both the offline and online paths read a single source of truth.
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure the context against a live connection and run migrations.

    ``render_as_batch`` is enabled so ALTER operations are emitted in SQLite's
    supported "batch" form (copy-and-move), keeping migrations portable between
    the SQLite dev database and Postgres in production. ``compare_type`` lets
    autogenerate detect column type changes.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations within an async connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # one-shot run: no need to keep a pool around
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against the async engine."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
