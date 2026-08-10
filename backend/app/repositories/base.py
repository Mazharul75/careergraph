"""Generic repository base.

The repository pattern puts every database query behind a named method. Callers ask for
``get_by_email(...)`` rather than assembling a ``select()`` themselves, so the persistence
details stay in one layer and can be swapped for a fake in tests.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base


# PEP 695 type-parameter syntax (Python 3.12). `[ModelT: Base]` declares a type variable bound
# to Base inline, replacing the older module-level TypeVar plus Generic[...] inheritance.
class BaseRepository[ModelT: Base]:
    """Shared CRUD operations for a single model.

    Subclasses set ``model`` and add query methods named for what the caller *wants*, not for
    how the SQL is shaped.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        # The session is injected, never constructed here. That is what lets a test bind the
        # repository to a transaction it can roll back.
        self._session = session

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self._session.get(self.model, entity_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> list[ModelT]:
        # Always paginated. An unbounded list() is a production incident waiting for the table
        # to get big enough.
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def add(self, entity: ModelT) -> ModelT:
        """Stage a new row.

        Deliberately does not commit. Transaction boundaries belong to the caller, which is
        what makes it possible to write two rows atomically — a user and their first resume,
        say — instead of leaving half a record behind when the second write fails.
        """
        self._session.add(entity)
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self._session.delete(entity)
