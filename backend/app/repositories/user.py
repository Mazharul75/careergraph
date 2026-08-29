"""User data access."""

from __future__ import annotations

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Every query against the ``users`` table lives here."""

    model = User

    async def get_by_email(self, email: str) -> User | None:
        """Look up an account by address.

        Normalises to lowercase so callers cannot accidentally miss an account by passing the
        address as the user typed it. The matching CHECK constraint on the column guarantees
        stored values are already lowercase, so this is a plain indexed equality lookup rather
        than a ``lower(email) = ...`` scan that could not use the index.
        """
        stmt = select(User).where(User.email == email.strip().lower())
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """Cheaper existence check for registration.

        Selects the primary key rather than the whole row — we only need to know whether the
        address is taken, not to load a password hash into memory.
        """
        stmt = select(User.id).where(User.email == email.strip().lower()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_by_google_sub(self, google_sub: str) -> User | None:
        """The fast path for a returning Google user: look up by Google's stable subject id
        rather than by email, which a person can change on either side of the link."""
        stmt = select(User).where(User.google_sub == google_sub)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
