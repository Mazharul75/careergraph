"""Resume data access."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import undefer

from app.models.resume import ParseStatus, Resume
from app.repositories.base import BaseRepository


class ResumeRepository(BaseRepository[Resume]):
    model = Resume

    async def get_for_user(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume | None:
        """Fetch a resume, scoped to its owner.

        The ``user_id`` predicate is the authorization check, and it belongs in the query rather
        than in an ``if`` after loading. Fetching first and comparing later is how one forgotten
        branch turns into an IDOR — any user reading any other user's resume by guessing an id.
        """
        stmt = select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID, *, limit: int = 50) -> list[Resume]:
        # `file_data` and `extracted_text` stay deferred here — a list view needs neither, and
        # loading them would drag megabytes of PDF per row across the wire.
        stmt = (
            select(Resume)
            .where(Resume.user_id == user_id)
            .order_by(Resume.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_text(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume | None:
        """Fetch a resume including its extracted text.

        Explicit `undefer` so the expensive column is loaded deliberately, at the one endpoint
        that actually needs it, rather than by accident everywhere.
        """
        stmt = (
            select(Resume)
            .where(Resume.id == resume_id, Resume.user_id == user_id)
            .options(undefer(Resume.extracted_text))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_pending_for_user(self, user_id: uuid.UUID) -> int:
        """How many of this user's resumes are still queued or in flight.

        Used to stop one account filling the queue while its earlier uploads are unprocessed.
        """
        stmt = select(Resume.id).where(
            Resume.user_id == user_id,
            Resume.status.in_((ParseStatus.PENDING, ParseStatus.PROCESSING)),
        )
        result = await self._session.execute(stmt)
        return len(list(result.scalars().all()))
