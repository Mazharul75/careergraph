"""Candidate ranking contracts."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.schemas.goal import GoalSkillGap


class RankedCandidateResponse(BaseModel):
    """One candidate row in a recruiter's ranked list.

    Carries a name and a score with its reasoning — and deliberately no email, no resume text,
    and no contact route. Ranking is a shortlisting aid; the recruiter reaching out is a
    separate act that should require the candidate's consent, not a field in this payload.
    """

    user_id: uuid.UUID
    full_name: str | None
    score: float = Field(ge=0, le=100)
    skill_coverage: float = Field(ge=0, le=1)
    semantic_similarity: float = Field(ge=0, le=1)
    matched: list[GoalSkillGap]
    missing: list[GoalSkillGap]
    has_resume: bool = Field(
        description="Whether the semantic half of the score had a resume embedding to use."
    )
