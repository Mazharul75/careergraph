"""Async engine, session factory, and the request-scoped session dependency."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_settings = get_settings()

# One engine per process. The engine owns a connection pool, so creating engines per request
# would open a new set of TCP connections every time — the single most common way to exhaust
# a Postgres connection limit.
engine: AsyncEngine = create_async_engine(
    str(_settings.database_url),
    echo=_settings.db_echo,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    # Recycle connections before managed Postgres providers silently drop idle ones.
    pool_recycle=1800,
    pool_pre_ping=True,
)

# expire_on_commit=False: by default SQLAlchemy marks every attribute stale after commit, so
# touching `user.email` afterwards triggers a fresh SELECT. In async code that lazy reload
# raises MissingGreenlet, because the implicit I/O happens outside an awaited call. Turning it
# off means committed objects stay usable, which is what route handlers actually need.
SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session scoped to a single request.

    The session is opened when the request starts and closed when it ends, on success or on
    exception alike. Committing is the caller's job — an implicit commit here would persist
    half-finished work from a request that later failed.
    """
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
