"""Operator-facing reads: fleet-wide counts and user administration.

Every query here crosses ownership boundaries, which is exactly why they are quarantined in
their own repository. A method that can read *all* users has no business sitting next to the
ones services call on behalf of a single account, where it could be reached by accident.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select

from app.models.career_goal import CareerGoal
from app.models.job import Job
from app.models.resume import ParseStatus, Resume
from app.models.user import User, UserRole
from app.models.user_skill import UserSkill
from app.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class SystemStats:
    total_users: int
    job_seekers: int
    recruiters: int
    admins: int
    inactive_users: int
    total_jobs: int
    public_jobs: int
    total_resumes: int
    resumes_pending: int
    resumes_failed: int
    active_goals: int
    achieved_goals: int


@dataclass(frozen=True, slots=True)
class AdminUserRow:
    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
    skill_count: int
    resume_count: int


class AdminRepository(BaseRepository[User]):
    model = User

    async def stats(self) -> SystemStats:
        """Fleet-wide counts, gathered with aggregate queries rather than loading rows.

        ``SELECT count(*)`` is answered by the database; ``len(await list_all())`` drags every
        row across the wire to be counted in Python. At ten users the difference is invisible,
        which is exactly why the habit has to be formed before it matters.
        """
        # .tuples().all() rather than passing the Result straight to dict(). A Result has a
        # .keys() method, so dict() takes it for a mapping and tries to subscript it, failing
        # with "ChunkedIteratorResult object is not subscriptable". .all() hands over a plain
        # list of rows, and .tuples() keeps them typed so these dicts need no cast.
        by_role: dict[UserRole, int] = dict(
            (await self._session.execute(select(User.role, func.count()).group_by(User.role)))
            .tuples()
            .all()
        )
        by_parse_status: dict[ParseStatus, int] = dict(
            (
                await self._session.execute(
                    select(Resume.status, func.count()).group_by(Resume.status)
                )
            )
            .tuples()
            .all()
        )

        async def count(stmt: Select[tuple[int]]) -> int:
            return int((await self._session.execute(stmt)).scalar_one())

        return SystemStats(
            total_users=await count(select(func.count()).select_from(User)),
            job_seekers=int(by_role.get(UserRole.JOB_SEEKER, 0)),
            recruiters=int(by_role.get(UserRole.RECRUITER, 0)),
            admins=int(by_role.get(UserRole.ADMIN, 0)),
            inactive_users=await count(
                select(func.count()).select_from(User).where(User.is_active.is_(False))
            ),
            total_jobs=await count(select(func.count()).select_from(Job)),
            public_jobs=await count(
                select(func.count()).select_from(Job).where(Job.is_public.is_(True))
            ),
            total_resumes=await count(select(func.count()).select_from(Resume)),
            resumes_pending=int(by_parse_status.get(ParseStatus.PENDING, 0))
            + int(by_parse_status.get(ParseStatus.PROCESSING, 0)),
            resumes_failed=int(by_parse_status.get(ParseStatus.FAILED, 0)),
            active_goals=await count(
                select(func.count()).select_from(CareerGoal).where(CareerGoal.achieved_at.is_(None))
            ),
            achieved_goals=await count(
                select(func.count())
                .select_from(CareerGoal)
                .where(CareerGoal.achieved_at.is_not(None))
            ),
        )

    async def list_users(self, *, limit: int = 50, offset: int = 0) -> list[AdminUserRow]:
        """Users with their activity counts, newest first.

        The two counts are correlated scalar subqueries rather than joins: joining to both
        collections would multiply rows and force a DISTINCT, and the subqueries let the
        database answer each count from an index on the foreign key.
        """
        skills_sq = (
            select(func.count())
            .select_from(UserSkill)
            .where(UserSkill.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        resumes_sq = (
            select(func.count())
            .select_from(Resume)
            .where(Resume.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )

        rows = (
            await self._session.execute(
                select(
                    User.id,
                    User.email,
                    User.full_name,
                    User.role,
                    User.is_active,
                    User.created_at,
                    skills_sq.label("skill_count"),
                    resumes_sq.label("resume_count"),
                )
                .order_by(User.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()

        return [
            AdminUserRow(
                id=row.id,
                email=row.email,
                full_name=row.full_name,
                role=row.role,
                is_active=row.is_active,
                created_at=row.created_at,
                skill_count=int(row.skill_count or 0),
                resume_count=int(row.resume_count or 0),
            )
            for row in rows
        ]

    async def list_all_jobs(self, *, limit: int = 50) -> list[Job]:
        stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
        return list((await self._session.execute(stmt)).scalars().all())
