"""Skill and skill-profile contracts."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.skill import SkillCategory
from app.models.user_skill import SkillSource, SkillStatus


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    canonical_name: str
    slug: str
    category: SkillCategory
    difficulty: int = Field(ge=1, le=5, description="Rough learning effort, 1-5.")


class UserSkillResponse(BaseModel):
    """One entry in the user's profile, with the skill inlined.

    Nested rather than returning bare ids: the client would otherwise have to fetch the whole
    113-skill vocabulary just to render a name.
    """

    model_config = ConfigDict(from_attributes=True)

    skill: SkillResponse
    source: SkillSource
    status: SkillStatus
    proficiency: int | None = Field(default=None, ge=1, le=5)
    occurrences: int


class SkillProfileResponse(BaseModel):
    confirmed: list[UserSkillResponse]
    suggested: list[UserSkillResponse]
    # Skills the user is actively working on. Kept as its own list rather than folded into
    # `suggested` because they mean opposite things: a suggestion is "we think you have this",
    # a learning entry is "you do not have this yet, and you are on it".
    learning: list[UserSkillResponse]
    total_confirmed: int
    total_suggested: int
    total_learning: int


class StartLearningRequest(BaseModel):
    skill_id: uuid.UUID


class AddSkillRequest(BaseModel):
    """Add a skill the extractor missed."""

    skill_id: uuid.UUID
    proficiency: int | None = Field(default=None, ge=1, le=5)


class UpdateSkillRequest(BaseModel):
    # Both optional so a client can confirm without setting proficiency, or set proficiency
    # without changing status.
    status: SkillStatus | None = None
    proficiency: int | None = Field(default=None, ge=1, le=5)
