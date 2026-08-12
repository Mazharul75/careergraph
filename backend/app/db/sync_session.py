"""Synchronous engine and session factory, for Celery workers only.

The API is fully async (ADR-0005). Celery is not: its workers are ordinary synchronous
processes with no event loop, and wrapping every task body in ``asyncio.run()`` would create
and destroy an event loop — and therefore a connection pool — per task, defeating pooling
exactly where throughput matters.

So the worker gets its own engine over the ``psycopg`` driver. Models, migrations, and
repositories are shared unchanged; only the engine and session differ.

**Do not import this from anything under ``app/api/``.** A synchronous query inside an async
request handler blocks the event loop for every concurrent request, not just its own.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

# A small pool. Worker concurrency is 1 on free hosting, and Neon's free tier caps connections
# — the API's pool and this one draw from the same budget.
sync_engine: Engine = create_engine(
    _settings.sync_database_url,
    echo=_settings.db_echo,
    pool_size=2,
    max_overflow=1,
    pool_recycle=1800,
    pool_pre_ping=True,
)

SyncSessionFactory = sessionmaker(bind=sync_engine, expire_on_commit=False, autoflush=False)


@contextmanager
def worker_session() -> Iterator[Session]:
    """A session scoped to one task execution.

    Commits on success, rolls back on any exception, and always closes. A task that raises
    must never leave a half-written row behind — Celery will retry it, and the retry has to
    start from a clean state for the task to be genuinely idempotent.
    """
    session = SyncSessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
