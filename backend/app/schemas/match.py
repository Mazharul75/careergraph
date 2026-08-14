"""Match score contracts."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SkillGapResponse(BaseModel):
    skill_id: uuid.UUID
    canonical_name: str
    importance: int = Field(ge=1, le=5)


class MatchResponse(BaseModel):
    """A score that explains itself.

    Every field beyond `score` exists so the number is defensible. A bare 73% tells a user
    nothing they can act on and gives them no reason to believe it.
    """

    job_id: uuid.UUID
    score: float = Field(ge=0, le=100, description="Overall fit, 0-100.")

    skill_coverage: float = Field(
        ge=0, le=1, description="Importance-weighted fraction of required skills held."
    )
    semantic_similarity: float = Field(
        ge=0, le=1, description="Cosine similarity between resume and job description."
    )
    semantic_available: bool = Field(
        description=(
            "False when the resume or job has not been embedded yet. The score is then based "
            "on skills alone and will change once embedding completes."
        )
    )

    matched: list[SkillGapResponse]
    missing: list[SkillGapResponse]
    total_required: int
