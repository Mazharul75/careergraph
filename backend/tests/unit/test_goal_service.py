"""GoalService against in-memory fakes.

The progress loop is the product's central mechanic, so it is tested where the rules live —
with no database, no HTTP, and no embedding model. Every assertion below is about *behaviour a
user would notice*: does starting to learn something leave the score alone, does finishing it
move the score, can two goals exist at once.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from app.core.config import get_settings
from app.models.career_goal import CareerGoal
from app.models.job import Job, JobSkill
from app.models.skill import Skill, SkillCategory
from app.models.user import User, UserRole
from app.models.user_skill import SkillSource, SkillStatus, UserSkill
from app.services.exceptions import (
    ActiveGoalExistsError,
    GoalNotAchievedError,
    GoalNotFoundError,
    JobNotFoundError,
)
from app.services.goal import ACHIEVEMENT_THRESHOLD, GoalService
from app.services.match import MatchService
from tests.unit.test_resume_service import FakeResumeRepository


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/careergraph_test")
    monkeypatch.setenv("JWT_SECRET_KEY", "unit-test-signing-key-not-used-anywhere-else")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:  # pragma: no cover - not exercised here
        pass


class FakeCareerGoalRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, CareerGoal] = {}

    async def get_active_for_user(self, user_id: uuid.UUID) -> CareerGoal | None:
        return next(
            (g for g in self.rows.values() if g.user_id == user_id and g.achieved_at is None),
            None,
        )

    async def get_owned(self, goal_id: uuid.UUID, user_id: uuid.UUID) -> CareerGoal | None:
        goal = self.rows.get(goal_id)
        return goal if goal and goal.user_id == user_id else None

    async def list_achieved_for_user(
        self, user_id: uuid.UUID, *, limit: int = 20
    ) -> list[CareerGoal]:
        return [
            g for g in self.rows.values() if g.user_id == user_id and g.achieved_at is not None
        ][:limit]

    def add(self, entity: CareerGoal) -> CareerGoal:
        # The real database assigns this default; in-memory we do it explicitly so the row is
        # addressable straight away.
        if entity.id is None:
            entity.id = uuid.uuid4()
        self.rows[entity.id] = entity
        return entity

    async def delete(self, entity: CareerGoal) -> None:
        self.rows.pop(entity.id, None)


class FakeJobRepository:
    """Implements the whole protocol, not just the methods these tests reach.

    ``mypy app tests`` type-checks the fakes against the protocols, so a partial fake is a
    build failure rather than a runtime AttributeError six months later — which is the point
    of depending on protocols at all.
    """

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Job] = {}

    async def get_visible(self, job_id: uuid.UUID, user_id: uuid.UUID) -> Job | None:
        job = self.rows.get(job_id)
        if job is None:
            return None
        # Mirrors the real query's WHERE clause: visibility is part of the lookup.
        return job if job.created_by == user_id or job.is_public else None

    async def get_owned(self, job_id: uuid.UUID, user_id: uuid.UUID) -> Job | None:
        job = self.rows.get(job_id)
        return job if job and job.created_by == user_id else None

    async def list_visible(self, user_id: uuid.UUID, *, limit: int = 50) -> list[Job]:
        return [j for j in self.rows.values() if j.created_by == user_id or j.is_public][:limit]

    async def list_public(self, *, limit: int = 50) -> list[Job]:
        return [j for j in self.rows.values() if j.is_public][:limit]

    async def reload(self, job_id: uuid.UUID) -> Job | None:
        return self.rows.get(job_id)

    async def replace_skills(self, job_id: uuid.UUID, entries: list[tuple[uuid.UUID, int]]) -> None:
        job = self.rows.get(job_id)
        if job is not None:
            job.required_skills = [
                JobSkill(job_id=job_id, skill_id=skill_id, importance=importance)
                for skill_id, importance in entries
            ]

    def add(self, entity: Job) -> Job:
        if entity.id is None:
            entity.id = uuid.uuid4()
        self.rows[entity.id] = entity
        return entity

    async def delete(self, entity: Job) -> None:
        self.rows.pop(entity.id, None)


class FakeUserSkillRepository:
    def __init__(self) -> None:
        self.rows: list[UserSkill] = []

    async def get(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> UserSkill | None:
        return next((r for r in self.rows if r.user_id == user_id and r.skill_id == skill_id), None)

    async def get_with_skill(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> UserSkill | None:
        return await self.get(user_id, skill_id)

    async def list_for_user(
        self, user_id: uuid.UUID, *, statuses: tuple[SkillStatus, ...] | None = None
    ) -> list[UserSkill]:
        return [
            r
            for r in self.rows
            if r.user_id == user_id and (statuses is None or r.status in statuses)
        ]

    async def rejected_skill_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        return {
            r.skill_id
            for r in self.rows
            if r.user_id == user_id and r.status is SkillStatus.REJECTED
        }

    async def upsert_extracted(
        self, user_id: uuid.UUID, matches: list[tuple[uuid.UUID, int]]
    ) -> int:
        for skill_id, occurrences in matches:
            existing = await self.get(user_id, skill_id)
            if existing is None:
                self.rows.append(
                    UserSkill(
                        user_id=user_id,
                        skill_id=skill_id,
                        source=SkillSource.EXTRACTED,
                        status=SkillStatus.SUGGESTED,
                        occurrences=occurrences,
                    )
                )
            elif existing.status is SkillStatus.SUGGESTED:
                existing.occurrences = occurrences
        return len(matches)

    def add(self, entity: UserSkill) -> UserSkill:
        self.rows.append(entity)
        return entity


# --------------------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------------------


def make_skill(name: str) -> Skill:
    return Skill(
        id=uuid.uuid4(),
        canonical_name=name,
        slug=name.lower(),
        category=SkillCategory.FRAMEWORK,
        difficulty=3,
    )


def make_job(owner: uuid.UUID, skills: list[Skill]) -> Job:
    job = Job(
        id=uuid.uuid4(),
        created_by=owner,
        title="Backend Engineer",
        description="x" * 40,
        is_public=False,
    )
    job.required_skills = [
        JobSkill(job_id=job.id, skill_id=s.id, importance=3, skill=s) for s in skills
    ]
    return job


class Harness:
    """Everything wired together, with helpers for the actions a user takes."""

    def __init__(self, required: int = 4) -> None:
        self.user = User(
            id=uuid.uuid4(),
            email="goal@example.com",
            password_hash="x",
            full_name="Goal Tester",
            role=UserRole.JOB_SEEKER,
            is_active=True,
        )
        self.skills = [make_skill(f"Skill{i}") for i in range(required)]
        self.job = make_job(self.user.id, self.skills)

        self.goals = FakeCareerGoalRepository()
        self.jobs = FakeJobRepository()
        self.jobs.rows[self.job.id] = self.job
        self.user_skills = FakeUserSkillRepository()
        self.uow = FakeUnitOfWork()

        # An empty resume repository, so no embedding exists and the score is skill-coverage
        # only. That keeps the arithmetic in every assertion something a reader can verify by
        # hand, instead of depending on a cosine similarity nobody can predict.
        matcher = MatchService(
            jobs=self.jobs, resumes=FakeResumeRepository(), user_skills=self.user_skills
        )
        self.service = GoalService(
            goals=self.goals,
            jobs=self.jobs,
            user_skills=self.user_skills,
            matcher=matcher,
            uow=self.uow,
        )

    def hold(self, *skills: Skill) -> None:
        """The user already has these skills."""
        for skill in skills:
            self.user_skills.rows.append(
                UserSkill(
                    user_id=self.user.id,
                    skill_id=skill.id,
                    source=SkillSource.MANUAL,
                    status=SkillStatus.CONFIRMED,
                    occurrences=0,
                )
            )

    def learning(self, *skills: Skill) -> None:
        for skill in skills:
            self.user_skills.rows.append(
                UserSkill(
                    user_id=self.user.id,
                    skill_id=skill.id,
                    source=SkillSource.MANUAL,
                    status=SkillStatus.LEARNING,
                    occurrences=0,
                )
            )

    def finish(self, skill: Skill) -> None:
        """The user finished learning a skill they had started."""
        for row in self.user_skills.rows:
            if row.skill_id == skill.id:
                row.status = SkillStatus.CONFIRMED


# --------------------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------------------


class TestSettingAGoal:
    async def test_freezes_the_current_score_as_the_baseline(self) -> None:
        harness = Harness(required=4)
        harness.hold(harness.skills[0])  # 1 of 4 → 25%

        progress = await harness.service.set_goal(user=harness.user, job_id=harness.job.id)

        assert progress.baseline_score == 25.0
        assert progress.current_score == 25.0
        assert progress.delta == 0.0

    async def test_rejects_a_second_active_goal(self) -> None:
        harness = Harness()
        await harness.service.set_goal(user=harness.user, job_id=harness.job.id)

        with pytest.raises(ActiveGoalExistsError):
            await harness.service.set_goal(user=harness.user, job_id=harness.job.id)

    async def test_rejects_a_job_the_user_cannot_see(self) -> None:
        harness = Harness()
        stranger_job = make_job(uuid.uuid4(), harness.skills)
        harness.jobs.rows[stranger_job.id] = stranger_job

        with pytest.raises(JobNotFoundError):
            await harness.service.set_goal(user=harness.user, job_id=stranger_job.id)


class TestTheProgressLoop:
    """The central mechanic: intention is free, completion is what counts."""

    async def test_starting_to_learn_does_not_move_the_score(self) -> None:
        harness = Harness(required=4)
        harness.hold(harness.skills[0])
        await harness.service.set_goal(user=harness.user, job_id=harness.job.id)

        harness.learning(harness.skills[1], harness.skills[2])
        progress = await harness.service.get_current(user=harness.user)

        assert progress is not None
        assert progress.current_score == 25.0, "declaring an intention must not earn score"
        assert progress.delta == 0.0
        assert len(progress.learning) == 2

    async def test_finishing_a_skill_moves_the_score_and_the_delta(self) -> None:
        harness = Harness(required=4)
        harness.hold(harness.skills[0])
        await harness.service.set_goal(user=harness.user, job_id=harness.job.id)

        harness.learning(harness.skills[1])
        harness.finish(harness.skills[1])

        progress = await harness.service.get_current(user=harness.user)
        assert progress is not None
        assert progress.current_score == 50.0  # 2 of 4
        assert progress.baseline_score == 25.0, "the baseline must never move"
        assert progress.delta == 25.0

    async def test_missing_skills_are_flagged_when_being_learned(self) -> None:
        harness = Harness(required=3)
        harness.hold(harness.skills[0])
        await harness.service.set_goal(user=harness.user, job_id=harness.job.id)
        harness.learning(harness.skills[1])

        progress = await harness.service.get_current(user=harness.user)

        assert progress is not None
        in_progress = set(progress.learning)
        assert harness.skills[1].id in in_progress
        assert harness.skills[2].id not in in_progress

    async def test_readiness_fills_the_bar_at_the_threshold_not_at_100(self) -> None:
        harness = Harness(required=4)
        harness.hold(*harness.skills)  # 100%
        progress = await harness.service.set_goal(user=harness.user, job_id=harness.job.id)

        assert progress.current_score == 100.0
        assert progress.readiness == 100.0
        assert progress.is_achievable_now

    async def test_readiness_is_relative_to_the_threshold(self) -> None:
        harness = Harness(required=4)
        harness.hold(harness.skills[0], harness.skills[1])  # 50%
        progress = await harness.service.set_goal(user=harness.user, job_id=harness.job.id)

        assert progress.current_score == 50.0
        assert progress.readiness == round(50.0 / ACHIEVEMENT_THRESHOLD * 100, 1)
        assert not progress.is_achievable_now


class TestAchievingAGoal:
    async def test_refuses_until_the_threshold_is_reached(self) -> None:
        harness = Harness(required=4)
        harness.hold(harness.skills[0])
        progress = await harness.service.set_goal(user=harness.user, job_id=harness.job.id)

        with pytest.raises(GoalNotAchievedError):
            await harness.service.mark_achieved(user=harness.user, goal_id=progress.goal.id)

    async def test_banks_the_goal_once_the_score_clears(self) -> None:
        harness = Harness(required=4)
        harness.hold(harness.skills[0])
        progress = await harness.service.set_goal(user=harness.user, job_id=harness.job.id)
        harness.hold(*harness.skills[1:])  # now 100%

        goal = await harness.service.mark_achieved(user=harness.user, goal_id=progress.goal.id)

        assert goal.achieved_at is not None
        assert not goal.is_active

    async def test_an_achieved_goal_frees_the_slot_for_a_new_one(self) -> None:
        harness = Harness(required=2)
        harness.hold(*harness.skills)
        progress = await harness.service.set_goal(user=harness.user, job_id=harness.job.id)
        await harness.service.mark_achieved(user=harness.user, goal_id=progress.goal.id)

        assert await harness.service.get_current(user=harness.user) is None
        # No ActiveGoalExistsError this time.
        await harness.service.set_goal(user=harness.user, job_id=harness.job.id)
        assert len(await harness.service.list_achievements(user=harness.user)) == 1

    async def test_another_users_goal_is_invisible(self) -> None:
        harness = Harness()
        progress = await harness.service.set_goal(user=harness.user, job_id=harness.job.id)
        stranger = User(
            id=uuid.uuid4(),
            email="other@example.com",
            password_hash="x",
            full_name="Other",
            role=UserRole.JOB_SEEKER,
            is_active=True,
        )

        with pytest.raises(GoalNotFoundError):
            await harness.service.abandon(user=stranger, goal_id=progress.goal.id)


class TestAbandoning:
    async def test_abandoning_frees_the_slot(self) -> None:
        harness = Harness()
        progress = await harness.service.set_goal(user=harness.user, job_id=harness.job.id)

        await harness.service.abandon(user=harness.user, goal_id=progress.goal.id)

        assert await harness.service.get_current(user=harness.user) is None
        # And it is not counted as an achievement.
        assert await harness.service.list_achievements(user=harness.user) == []
