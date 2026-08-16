"""Career goal contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.job import JobSummary


class SetGoalRequest(BaseModel):
    job_id: uuid.UUID


class GoalSkillGap(BaseModel):
    """A required skill, and whether the user is actively working on it.

    ``is_learning`` is what lets the UI show three states instead of two — held, in progress,
    not started — which is the difference between a checklist and a plan someone is following.
    """

    skill_id: uuid.UUID
    canonical_name: str
    importance: int = Field(ge=1, le=5)
    is_learning: bool = False


class GoalProgressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job: JobSummary
    created_at: datetime
    achieved_at: datetime | None

    baseline_score: float = Field(description="Match score when the goal was set, frozen.")
    current_score: float
    delta: float = Field(description="current_score - baseline_score. Negative is possible.")
    readiness: float = Field(ge=0, le=100, description="Progress toward the achievement bar.")
    is_achievable_now: bool

    matched: list[GoalSkillGap]
    missing: list[GoalSkillGap]
    learning_count: int

    semantic_available: bool = Field(
        description="False while the embedding is still being computed; the score is skill-only."
    )


class AchievementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job: JobSummary
    baseline_score: float
    created_at: datetime
    achieved_at: datetime | None
