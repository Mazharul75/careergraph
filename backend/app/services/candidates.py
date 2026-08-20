"""Ranking candidates for a job posting — the recruiter half of the product.

This is the same engine as the job-seeker match, pointed the other way. A job seeker asks
"how do I score against these jobs?"; a recruiter asks "how do these people score against my
job?" Both are `score_match`, so the two sides can never disagree about what a 62% means.

**What a recruiter is deliberately not shown:** resume text, contact details beyond the name,
or any skill the candidate rejected. A ranked list is a hiring aid; handing over the documents
people uploaded for their own planning would be a different product, and a worse one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.user import User
from app.models.user_skill import SkillStatus
from app.repositories.protocols import (
    CandidateRepositoryProtocol,
    JobRepositoryProtocol,
    ResumeRepositoryProtocol,
)
from app.services.embedding import cosine_similarity
from app.services.exceptions import JobNotFoundError, NotYourJobError
from app.services.matching import RequiredSkill, SkillGap, score_match


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """One candidate, with the reasoning a recruiter needs to trust the number."""

    user_id: uuid.UUID
    full_name: str | None
    score: float
    skill_coverage: float
    semantic_similarity: float
    matched: tuple[SkillGap, ...]
    missing: tuple[SkillGap, ...]
    has_resume: bool


class CandidateService:
    def __init__(
        self,
        *,
        jobs: JobRepositoryProtocol,
        candidates: CandidateRepositoryProtocol,
        resumes: ResumeRepositoryProtocol,
    ) -> None:
        self._jobs = jobs
        self._candidates = candidates
        self._resumes = resumes

    async def rank_for_job(
        self, *, recruiter: User, job_id: uuid.UUID, limit: int = 50
    ) -> list[RankedCandidate]:
        """Rank every job seeker against one of the recruiter's own postings.

        Ownership is checked first and separately from visibility: a recruiter may *see* other
        people's public postings, but ranking candidates against a posting they do not own
        would leak the talent pool to anyone who can read a job id.
        """
        job = await self._jobs.get_visible(job_id, recruiter.id)
        if job is None:
            raise JobNotFoundError
        if job.created_by != recruiter.id:
            raise NotYourJobError

        required = tuple(
            RequiredSkill(
                skill_id=js.skill_id,
                canonical_name=js.skill.canonical_name,
                importance=js.importance,
            )
            for js in job.required_skills
        )

        # One query for every candidate's skills, not one query per candidate. With a
        # per-candidate loop this endpoint would issue N+1 queries and get slower as the
        # product succeeds — the worst possible scaling shape.
        profiles = await self._candidates.load_candidate_profiles(
            statuses=SkillStatus.counts_as_held(), limit=limit
        )

        ranked: list[RankedCandidate] = []
        for profile in profiles:
            similarity: float | None = None
            if profile.resume_embedding is not None and job.embedding is not None:
                similarity = cosine_similarity(list(profile.resume_embedding), list(job.embedding))

            result = score_match(
                user_skill_ids=profile.skill_ids,
                required=required,
                semantic_similarity=similarity,
            )

            # Candidates with nothing in common are noise, not signal. A recruiter scrolling
            # past forty 0% rows learns nothing and stops trusting the list.
            if result.score <= 0:
                continue

            ranked.append(
                RankedCandidate(
                    user_id=profile.user_id,
                    full_name=profile.full_name,
                    score=result.score,
                    skill_coverage=result.skill_coverage,
                    semantic_similarity=result.semantic_similarity,
                    matched=result.matched,
                    missing=result.missing,
                    has_resume=profile.resume_embedding is not None,
                )
            )

        ranked.sort(key=lambda c: -c.score)
        return ranked[:limit]
