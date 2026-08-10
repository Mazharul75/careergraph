"""Alembic environment, wired for an async engine.

The stock Alembic template is synchronous. Because the application uses asyncpg, migrations
must open an async connection and then hand a *sync-style* connection to Alembic's migration
context via ``connection.run_sync(...)`` — Alembic's internals are synchronous and are not
being rewritten here.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings

# Importing the models package populates Base.metadata. Without this import, autogenerate sees
# an empty schema and proposes dropping every table in the database.
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the URL from application settings rather than alembic.ini, so credentials live only
# in the environment and migrations can never run against the wrong database by accident.
config.set_main_option("sqlalchemy.url", str(get_settings().database_url))

target_metadata = Base.metadata


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detect column type changes (VARCHAR(100) -> VARCHAR(200)). Off by default, and its
        # absence is why people find autogenerate "misses things".
        compare_type=True,
        # Detect changes to server-side defaults.
        compare_server_default=True,
        # Wrap each migration in its own transaction so a failure rolls back cleanly.
        transaction_per_migration=True,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting.

    Used to generate a script for a DBA to review — useful when production access is
    restricted and someone else applies the change.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Connect and apply migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        # NullPool: a migration run is a short-lived process. Pooling would hold connections
        # open after the work is done and delay process exit.
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
