"""Alembic migration environment — SQLAlchemy async.

T027: Replaces Prisma migrate with Alembic for schema migrations.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

# Load .env so `DATABASE_URL` is in the environment when alembic is run
# without first exporting it manually. Existing shell env wins.
try:
    from dotenv import load_dotenv
    _backend_env = Path(__file__).resolve().parents[1] / ".env"
    if _backend_env.exists():
        load_dotenv(_backend_env, override=False)
except ImportError:
    pass

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from app.db import Base, normalize_database_url
from app.models import (
    ChatMessage,
    ChatSession,
    MagicLinkToken,
    Model,
    Provider,
    TokenUsageLog,
    User,
    UserPreference,
)

config = context.config

# Normalize the database URL: prefer $DATABASE_URL, fall back to
# `sqlalchemy.url` in alembic.ini. `normalize_database_url` upgrades
# `postgresql://` → `postgresql+asyncpg://` and pulls `sslmode=...` out of
# the query string into `connect_args` for asyncpg.
_db_url, _db_connect_args = normalize_database_url(
    os.environ.get(
        "DATABASE_URL",
        config.get_main_option("sqlalchemy.url") or "",
    ).strip()
)
config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    # We build the engine directly (not via async_engine_from_config) so we
    # can pass `connect_args` as a real dict, not a config-stringified one.
    connectable = create_async_engine(
        _db_url,
        echo=False,
        poolclass=pool.NullPool,
        future=True,
        connect_args=_db_connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    import asyncio
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
