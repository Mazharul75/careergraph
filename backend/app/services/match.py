"""Orchestration for scoring a user against a job.

Thin by design: the scoring rules live in ``matching.py`` as pure functions, and this class
only gathers the inputs those functions need.
"""

from __future__ import annotations

import uuid

from app.models.user import User
from app.models.user_skill import SkillStatus
from app.repositories.protocols import (
    JobRepositoryProtocol,
    ResumeRepositoryProtocol,
    UserSkillRepositoryProtocol,
)
from app.services.embedding import cosine_similarity
from app.services.exceptions import JobNotFoundError
from app.services.matching import MatchResult, RequiredSkill, score_match


class MatchService:
    def __init__(
        self,
        *,
        jobs: JobRepositoryProtocol,
        resumes: ResumeRepositoryProtocol,
        user_skills: UserSkillRepositoryProtocol,
    ) -> None:
        self._jobs = jobs
        self._resumes = resumes
        self._user_skills = user_skills

    async def score(self, *, user: User, job_id: uuid.UUID) -> tuple[MatchResult, bool]:
        """Score a user's profile against a job.

        Returns ``(result, semantic_available)`` so the API can tell the client whether the
        semantic component actually contributed, rather than leaving them to guess why a score
        moved after a refresh.
        """
        job = await self._jobs.get_visible(job_id, user.id)
        if job is None:
            raise JobNotFoundError

        # Suggested skills count, not just confirmed ones. A user who has uploaded a resume but
        # not yet reviewed the suggestions should still get a meaningful score — requiring
        # review first would show everyone 0% on their first visit, which reads as broken.
        # Rejected skills are excluded, because rejection is an explicit "I do not have this",
        # and so are skills being *learned* — see SkillStatus.counts_as_held.
        entries = await self._user_skills.list_for_user(
            user.id, statuses=SkillStatus.counts_as_held()
        )
        user_skill_ids = frozenset(entry.skill_id for entry in entries)

        required = tuple(
            RequiredSkill(
                skill_id=js.skill_id,
                canonical_name=js.skill.canonical_name,
                importance=js.importance,
            )
            for js in job.required_skills
        )

        similarity: float | None = None
        resume = await self._resumes.latest_embedded_for_user(user.id)
        if resume is not None and resume.embedding is not None and job.embedding is not None:
            similarity = cosine_similarity(list(resume.embedding), list(job.embedding))

        return score_match(
            user_skill_ids=user_skill_ids,
            required=required,
            semantic_similarity=similarity,
        ), similarity is not None
