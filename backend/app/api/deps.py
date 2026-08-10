"""Shared FastAPI dependencies.

Dependency injection here means a route declares *what it needs* in its signature and FastAPI
supplies it. Nothing constructs its own database session or repository, so a test can swap any
of them out through ``app.dependency_overrides`` without patching module globals.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.user import UserRepository

# Annotated aliases keep route signatures readable. Without this, every handler needing a
# session repeats `session: AsyncSession = Depends(get_db)`.
DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_user_repository(session: DbSession) -> UserRepository:
    """Build a UserRepository bound to the current request's session."""
    return UserRepository(session)


UserRepo = Annotated[UserRepository, Depends(get_user_repository)]
