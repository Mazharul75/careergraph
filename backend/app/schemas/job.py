"""Job contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.skill import SkillResponse


class JobSkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill: SkillResponse
    importance: int = Field(ge=1, le=5)


class CreateJobRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    # 30 characters minimum, matched by a CHECK constraint. Below that there is nothing to
    # extract skills from, and a one-word "job description" produces a meaningless match score.
    description: str = Field(min_length=30, max_length=50_000)
    company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    is_public: bool = Field(
        default=False,
        description="Recruiters only. A public posting is visible to all users.",
    )

    @field_validator("title", "company", "location")
    @classmethod
    def strip_whitespace(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class UpdateJobRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=30, max_length=50_000)
    company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company: str | None
    location: str | None
    description: str
    is_public: bool
    created_by: uuid.UUID
    required_skills: list[JobSkillResponse]
    created_at: datetime
    updated_at: datetime


class JobSummary(BaseModel):
    """List view. Omits the full description, which can be 50 KB."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company: str | None
    location: str | None
    is_public: bool
    created_by: uuid.UUID
    skill_count: int = 0
    created_at: datetime
