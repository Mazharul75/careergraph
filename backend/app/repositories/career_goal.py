"""Career goal data access."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import joinedload

from app.models.career_goal import CareerGoal
from app.models.job import Job, JobSkill
from app.repositories.base import BaseRepository


def _with_job() -> Select[tuple[CareerGoal]]:
    # The goal is never useful without its job, and the job is never useful without its
    # required skills — scoring needs them immediately. Loading all three in one query keeps
    # this off the N+1 path, and in async SQLAlchemy a missed eager load is not merely slow:
    # it raises MissingGreenlet at render time.
    return select(CareerGoal).options(
        joinedload(CareerGoal.job).selectinload(Job.required_skills).joinedload(JobSkill.skill)
    )


class CareerGoalRepository(BaseRepository[CareerGoal]):
    model = CareerGoal

    async def get_active_for_user(self, user_id: uuid.UUID) -> CareerGoal | None:
        """The user's one live goal, if they have one.

        ``achieved_at IS NULL`` is the same predicate as the partial unique index, so this can
        never legitimately match more than one row.
        """
        stmt = _with_job().where(CareerGoal.user_id == user_id, CareerGoal.achieved_at.is_(None))
        result = await self._session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_owned(self, goal_id: uuid.UUID, user_id: uuid.UUID) -> CareerGoal | None:
        """Ownership is in the WHERE clause, not checked after loading.

        Same reasoning as jobs and resumes: a filter that must be remembered separately is one
        that eventually gets forgotten, and forgetting it here would let anyone read or delete
        another user's goal by id.
        """
        stmt = _with_job().where(CareerGoal.id == goal_id, CareerGoal.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def list_achieved_for_user(
        self, user_id: uuid.UUID, *, limit: int = 20
    ) -> list[CareerGoal]:
        """Completed goals, newest first — the user's track record."""
        stmt = (
            _with_job()
            .where(CareerGoal.user_id == user_id, CareerGoal.achieved_at.is_not(None))
            .order_by(CareerGoal.achieved_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.unique().scalars().all())

    async def delete(self, entity: CareerGoal) -> None:
        await self._session.delete(entity)
