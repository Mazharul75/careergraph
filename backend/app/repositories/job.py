"""Job data access."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, delete, or_, select
from sqlalchemy.orm import selectinload, undefer

from app.models.job import Job, JobSkill
from app.repositories.base import BaseRepository


def _with_skills() -> Select[tuple[Job]]:
    # Eager-load the join rows and the skills behind them. Without this, rendering a job's
    # required skills issues one query per skill (N+1), and in async SQLAlchemy it raises
    # MissingGreenlet rather than merely being slow.
    return select(Job).options(selectinload(Job.required_skills).joinedload(JobSkill.skill))


class JobRepository(BaseRepository[Job]):
    model = Job

    async def get_visible(self, job_id: uuid.UUID, user_id: uuid.UUID) -> Job | None:
        """A job the user is allowed to see: their own, or any public posting.

        Visibility is part of the WHERE clause rather than a check after loading — the same
        reasoning as resumes. A forgotten branch after the fact is how private data leaks.

        ``undefer(Job.embedding)`` is load-bearing. The column is deferred, so scoring code
        that reads ``job.embedding`` triggers lazy I/O — which in async SQLAlchemy is not
        merely slow, it raises MissingGreenlet. This stayed hidden for a long time because
        every caller short-circuits on the *resume* embedding first: with no embedded resume
        in the database, ``job.embedding`` was never reached. The moment real resumes finished
        embedding, every match and every candidate ranking started returning 500.

        Only on the single-job read. ``list_visible`` deliberately leaves it deferred — a list
        page has no use for 384 floats per row.
        """
        stmt = (
            _with_skills()
            .options(undefer(Job.embedding))
            .where(
                Job.id == job_id,
                or_(Job.created_by == user_id, Job.is_public.is_(True)),
            )
        )
        result = await self._session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_owned(self, job_id: uuid.UUID, user_id: uuid.UUID) -> Job | None:
        """A job the user may modify. Public postings owned by someone else are excluded."""
        stmt = _with_skills().where(Job.id == job_id, Job.created_by == user_id)
        result = await self._session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def list_visible(self, user_id: uuid.UUID, *, limit: int = 50) -> list[Job]:
        stmt = (
            _with_skills()
            .where(or_(Job.created_by == user_id, Job.is_public.is_(True)))
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.unique().scalars().all())

    async def replace_skills(self, job_id: uuid.UUID, entries: list[tuple[uuid.UUID, int]]) -> None:
        """Set a job's required skills, replacing whatever was there.

        Deliberately does NOT assign to `job.required_skills`. Assigning a collection on a
        persistent object makes SQLAlchemy lazy-load the current collection first, to work out
        which rows to orphan — and that implicit load is I/O outside an await, which raises
        MissingGreenlet in async SQLAlchemy. A DELETE followed by inserts expresses the same
        intent with no hidden query.
        """
        await self._session.execute(delete(JobSkill).where(JobSkill.job_id == job_id))
        self._session.add_all(
            [
                JobSkill(job_id=job_id, skill_id=skill_id, importance=importance)
                for skill_id, importance in entries
            ]
        )

    async def reload(self, job_id: uuid.UUID) -> Job | None:
        """Re-read a job with its skills eagerly loaded, ready to serialise.

        JobSkill rows built in Python have no `.skill` populated — `lazy="joined"` applies to
        queries, not to objects constructed in memory — so serialising a freshly created job
        would attempt lazy I/O and raise MissingGreenlet.

        `populate_existing` forces the eager load to overwrite what the identity map already
        holds; without it SQLAlchemy hands back the same unloaded instances.
        """
        stmt = _with_skills().where(Job.id == job_id).execution_options(populate_existing=True)
        result = await self._session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def list_public(self, *, limit: int = 50) -> list[Job]:
        stmt = (
            _with_skills()
            .where(Job.is_public.is_(True))
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.unique().scalars().all())
