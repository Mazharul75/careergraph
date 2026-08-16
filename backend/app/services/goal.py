"""Career goals — the loop that makes this a product rather than a report.

Scoring a resume against a job answers "where do I stand?" once. That is a *report*: nothing
the user does changes it, and there is no reason to return. A goal adds the missing axis —
time — by freezing the score at the moment it was set. Everything after that is measured
against it, so studying a skill produces a number that visibly moves.

The mechanic rests on one deliberate rule, defined on ``SkillStatus.counts_as_held``: a skill
marked *learning* does not count toward the score. Only marking it *confirmed* — "I have
actually learned this" — moves the number. Declaring an intention costs nothing and earns
nothing, which is what keeps the score honest.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.career_goal import CareerGoal
from app.models.user import User
from app.models.user_skill import SkillStatus
from app.repositories.protocols import (
    CareerGoalRepositoryProtocol,
    JobRepositoryProtocol,
    UnitOfWork,
    UserSkillRepositoryProtocol,
)
from app.services.exceptions import (
    ActiveGoalExistsError,
    GoalNotAchievedError,
    GoalNotFoundError,
    JobNotFoundError,
)
from app.services.match import MatchService
from app.services.matching import SkillGap

# A goal counts as reached at this score rather than at 100. A perfect match is not the bar
# anyone actually clears — job postings list aspirational requirements, and demanding every
# one would mean the goal is never achievable and the user never gets the payoff.
ACHIEVEMENT_THRESHOLD = 85.0


@dataclass(frozen=True, slots=True)
class GoalProgress:
    """A goal with its journey attached, ready to render."""

    goal: CareerGoal
    baseline_score: float
    current_score: float
    matched: tuple[SkillGap, ...]
    missing: tuple[SkillGap, ...]
    learning: tuple[uuid.UUID, ...]
    semantic_available: bool

    @property
    def delta(self) -> float:
        """How far the user has moved since setting the goal. Can be negative."""
        return round(self.current_score - self.baseline_score, 1)

    @property
    def is_achievable_now(self) -> bool:
        return self.current_score >= ACHIEVEMENT_THRESHOLD

    @property
    def readiness(self) -> float:
        """Progress toward the *threshold*, 0-100, for a progress bar.

        Measured against the achievement bar rather than a raw 100, so a filled bar and the
        "goal reached" state mean the same thing. Nothing is more deflating than a bar that
        looks full while the app insists you are not done.
        """
        return round(min(100.0, self.current_score / ACHIEVEMENT_THRESHOLD * 100), 1)


class GoalService:
    def __init__(
        self,
        *,
        goals: CareerGoalRepositoryProtocol,
        jobs: JobRepositoryProtocol,
        user_skills: UserSkillRepositoryProtocol,
        matcher: MatchService,
        uow: UnitOfWork,
    ) -> None:
        self._goals = goals
        self._jobs = jobs
        self._user_skills = user_skills
        self._matcher = matcher
        self._uow = uow

    async def set_goal(self, *, user: User, job_id: uuid.UUID) -> GoalProgress:
        """Adopt a job as the user's target.

        The current match score is computed and stored as the baseline *before* anything else,
        because after this moment it can never be recovered — the user's skills will have
        changed, and that change is exactly what we are trying to measure.
        """
        existing = await self._goals.get_active_for_user(user.id)
        if existing is not None:
            raise ActiveGoalExistsError

        job = await self._jobs.get_visible(job_id, user.id)
        if job is None:
            raise JobNotFoundError

        result, _semantic = await self._matcher.score(user=user, job_id=job_id)

        goal = CareerGoal(user_id=user.id, job_id=job_id, baseline_score=result.score)
        self._goals.add(goal)
        await self._uow.commit()

        # Re-read so the job relationship is populated. A freshly constructed entity has no
        # relationship loaded, and serialising one raises MissingGreenlet rather than lazily
        # fetching it — the async-SQLAlchemy trap recorded in the project gotchas.
        stored = await self._goals.get_active_for_user(user.id)
        assert stored is not None  # noqa: S101 - just committed it
        return await self._progress_for(user=user, goal=stored)

    async def get_current(self, *, user: User) -> GoalProgress | None:
        """The active goal with its progress, or None if the user has not set one."""
        goal = await self._goals.get_active_for_user(user.id)
        if goal is None:
            return None
        return await self._progress_for(user=user, goal=goal)

    async def abandon(self, *, user: User, goal_id: uuid.UUID) -> None:
        """Drop an active goal so a different one can be set.

        Deleted rather than tombstoned. An abandoned goal is not an achievement and not
        history worth showing; keeping it would only complicate every later read.
        """
        goal = await self._goals.get_owned(goal_id, user.id)
        if goal is None:
            raise GoalNotFoundError
        await self._goals.delete(goal)
        await self._uow.commit()

    async def mark_achieved(self, *, user: User, goal_id: uuid.UUID) -> CareerGoal:
        """Bank a goal the user has reached.

        Requires the score to actually clear the threshold. Letting anyone mark any goal
        achieved would make the achievement meaningless — the point is that the system
        verifies it, not that the user asserts it.
        """
        goal = await self._goals.get_owned(goal_id, user.id)
        if goal is None or goal.achieved_at is not None:
            raise GoalNotFoundError

        progress = await self._progress_for(user=user, goal=goal)
        if not progress.is_achievable_now:
            raise GoalNotAchievedError

        goal.achieved_at = datetime.now(UTC)
        await self._uow.commit()
        return goal

    async def list_achievements(self, *, user: User) -> list[CareerGoal]:
        return await self._goals.list_achieved_for_user(user.id)

    async def _progress_for(self, *, user: User, goal: CareerGoal) -> GoalProgress:
        result, semantic_available = await self._matcher.score(user=user, job_id=goal.job_id)

        learning = await self._user_skills.list_for_user(user.id, statuses=(SkillStatus.LEARNING,))

        return GoalProgress(
            goal=goal,
            baseline_score=goal.baseline_score,
            current_score=result.score,
            matched=result.matched,
            missing=result.missing,
            learning=tuple(entry.skill_id for entry in learning),
            semantic_available=semantic_available,
        )
