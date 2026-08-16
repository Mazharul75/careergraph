"""Shared pytest fixtures.

Test isolation strategy: the schema is created **once per session by running the real Alembic
migrations**, and each test runs inside a transaction that is rolled back afterwards.

Two things follow from that:

1. The migrations are themselves under test. A migration that doesn't apply cleanly fails the
   whole suite immediately, rather than being discovered during a deploy.
2. Tests cannot leak state into one another, and the suite stays fast — a rollback is far
   cheaper than dropping and recreating tables between tests.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine

from app.core.config import Settings, get_settings


def _resolve_test_database_url() -> str:
    """Work out which database the suite may touch, and refuse anything suspicious.

    Read through a throwaway ``Settings`` instance rather than ``os.environ`` directly, because
    ``TEST_DATABASE_URL`` normally lives in the ``.env`` file and is not exported into the
    process environment. Reading os.environ here silently returns None, the redirect below
    never happens, and migrations get applied to the development database while tests query an
    empty test database — a confusing failure that looks like broken migrations.
    """
    bootstrap = Settings()  # type: ignore[call-arg]
    url = str(bootstrap.test_database_url or bootstrap.database_url)

    # The suite creates and rolls back transactions against whatever this points at. If it were
    # ever a development or production database, a bad fixture could destroy real data. This
    # check costs nothing and removes the possibility.
    if "test" not in url.rsplit("/", 1)[-1]:
        raise RuntimeError(
            f"Refusing to run tests against {url!r}: the database name must contain 'test'. "
            "Set TEST_DATABASE_URL to a dedicated test database."
        )
    return url


# This runs at import time, before any application module that builds an engine is imported,
# so `app.db.session` constructs its engine against the test database rather than the
# development one. The cache_clear() is essential: get_settings() is lru_cached and was just
# populated by the bootstrap read above.
TEST_DATABASE_URL = _resolve_test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Rate limiting is off by default for the whole suite: hundreds of tests log in from the same
# fake client address, which is exactly the traffic pattern the limiter exists to reject. The
# dedicated rate-limit tests re-enable it explicitly with their own tight limits.
os.environ["RATE_LIMIT_ENABLED"] = "false"
get_settings.cache_clear()

from app.api.deps import get_db  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session")
def database_url() -> str:
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def apply_migrations(database_url: str) -> None:
    """Bring the test database to head before any test runs.

    Synchronous on purpose. Alembic's env.py calls ``asyncio.run()`` internally, which would
    raise if invoked from inside pytest-asyncio's already-running event loop.
    """
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
async def engine(database_url: str, apply_migrations: None) -> AsyncGenerator[AsyncEngine, None]:
    test_engine = create_async_engine(database_url, echo=False)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def connection(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    """A connection with an open outer transaction, rolled back after each test."""
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()


@pytest.fixture
async def db_session(connection: AsyncConnection) -> AsyncGenerator[AsyncSession, None]:
    """A session bound to the test transaction.

    ``join_transaction_mode="create_savepoint"`` is the important part: when application code
    calls ``session.commit()``, SQLAlchemy releases a SAVEPOINT rather than committing the
    outer transaction. The code under test sees a real commit; the outer rollback still undoes
    everything. This is how you test commit behaviour without persisting anything.
    """
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture
def app(db_session: AsyncSession) -> Generator[FastAPI, None, None]:
    """A fresh application instance with the database dependency overridden.

    Exposed as its own fixture (rather than built inside ``client``) so tests can install
    additional ``dependency_overrides`` — the rate-limit tests swap the Redis-backed limiter
    for an in-memory one this way.
    """
    application = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """An HTTP client wired to the app.

    ``ASGITransport`` calls the ASGI application in-process — no socket, no live server. The
    request path is otherwise identical to production: real routing, real middleware, real
    dependency resolution, real validation.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
