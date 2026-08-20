"""Candidate pool data access — reading many users' profiles in one pass.

Kept apart from ``UserRepository`` because it answers a different question. That repository
serves authentication: one account, by id or address. This one serves ranking: every job
seeker's *skills*, in bulk, with no password hashes anywhere near the result.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select

from app.models.resume import ParseStatus, Resume
from app.models.user import User, UserRole
from app.models.user_skill import SkillStatus, UserSkill
from app.repositories.base import BaseRepository


@dataclass(slots=True)
class CandidateProfile:
    """A candidate reduced to exactly what scoring needs, and nothing else.

    Deliberately not a ``User``. Passing ORM users into the ranking service would put a
    password hash one attribute access away from a response model; this cannot leak what it
    does not carry.
    """

    user_id: uuid.UUID
    full_name: str | None
    skill_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    resume_embedding: list[float] | None = None


class CandidateRepository(BaseRepository[User]):
    model = User

    async def load_candidate_profiles(
        self, *, statuses: tuple[SkillStatus, ...], limit: int = 50
    ) -> list[CandidateProfile]:
        """Every active job seeker with at least one skill, in three queries total.

        Three queries rather than one join, on purpose: joining users to skills to resumes
        multiplies rows by both collections, and reassembling that in Python is more code and
        more memory than issuing three flat reads and zipping them by id.
        """
        user_rows = (
            await self._session.execute(
                select(User.id, User.full_name)
                .where(User.role == UserRole.JOB_SEEKER, User.is_active.is_(True))
                .order_by(User.created_at.desc())
                .limit(limit)
            )
        ).all()
        if not user_rows:
            return []

        profiles = {
            row.id: CandidateProfile(user_id=row.id, full_name=row.full_name) for row in user_rows
        }

        skill_rows = (
            await self._session.execute(
                select(UserSkill.user_id, UserSkill.skill_id).where(
                    UserSkill.user_id.in_(profiles.keys()), UserSkill.status.in_(statuses)
                )
            )
        ).all()

        grouped: dict[uuid.UUID, set[uuid.UUID]] = {}
        for user_id, skill_id in skill_rows:
            grouped.setdefault(user_id, set()).add(skill_id)
        for user_id, skill_ids in grouped.items():
            profiles[user_id].skill_ids = frozenset(skill_ids)

        resume_rows = (
            await self._session.execute(
                select(Resume.user_id, Resume.embedding)
                .where(
                    Resume.user_id.in_(profiles.keys()),
                    Resume.status == ParseStatus.COMPLETE,
                    Resume.embedding.is_not(None),
                )
                .order_by(Resume.created_at.desc())
            )
        ).all()
        for user_id, embedding in resume_rows:
            # Newest first, so the first row seen for a user is their latest resume; later
            # ones are older versions and must not overwrite it.
            if profiles[user_id].resume_embedding is None and embedding is not None:
                profiles[user_id].resume_embedding = list(embedding)

        # A candidate with no skills at all cannot be scored against anything.
        return [p for p in profiles.values() if p.skill_ids]
