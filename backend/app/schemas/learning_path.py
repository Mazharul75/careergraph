"""Learning path contracts."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class PathStepResponse(BaseModel):
    order: int = Field(ge=1, description="1-based position in the plan.")
    skill_id: uuid.UUID
    canonical_name: str
    slug: str
    difficulty: int = Field(ge=1, le=5)

    directly_required: bool = Field(
        description=(
            "True when the job named this skill. False when it was pulled in as a "
            "prerequisite the posting never mentioned."
        )
    )
    unlocked_by: list[str] = Field(
        default_factory=list,
        description="Earlier steps in this plan that must be completed first.",
    )


class LearningPathResponse(BaseModel):
    """An ordered plan, not a list of gaps.

    The ordering is the product: every step appears after everything it depends on, which is a
    guarantee a set difference cannot make.
    """

    steps: list[PathStepResponse]
    step_count: int
    total_effort: int = Field(
        description="Sum of step difficulties — a rough measure of how much learning is ahead."
    )
    unreachable: list[str] = Field(
        default_factory=list,
        description="Required skills absent from the graph, so no path could be computed.",
    )


class SkillPathResponse(LearningPathResponse):
    """A plan for one skill, plus the single cheapest route to it."""

    shortest_route: list[str] = Field(
        default_factory=list,
        description=(
            "The least-effort chain from something you already know to the target, weighted "
            "by difficulty rather than hop count."
        ),
    )
