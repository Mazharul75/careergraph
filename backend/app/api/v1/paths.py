"""Learning-path routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, LearningPathServiceDep
from app.schemas.learning_path import (
    LearningPathResponse,
    PathStepResponse,
    SkillPathResponse,
)
from app.services.skill_graph import LearningPath

router = APIRouter()


def _steps(path: LearningPath) -> list[PathStepResponse]:
    return [
        PathStepResponse(
            order=step.order,
            skill_id=step.skill_id,
            canonical_name=step.canonical_name,
            slug=step.slug,
            difficulty=step.difficulty,
            directly_required=step.directly_required,
            unlocked_by=list(step.unlocked_by),
        )
        for step in path.steps
    ]


@router.get(
    "/jobs/{job_id}/learning-path",
    response_model=LearningPathResponse,
    tags=["learning-path"],
    summary="An ordered plan to close the gap for a job",
    responses={404: {"description": "No such job, or it is private and not yours"}},
)
async def job_learning_path(
    job_id: uuid.UUID, current_user: CurrentUser, paths: LearningPathServiceDep
) -> LearningPathResponse:
    """Returns skills in an order you can actually follow.

    Every step appears after everything it depends on — a topological ordering of the
    prerequisite graph, restricted to what this user is missing. Steps marked
    `directly_required: false` were never mentioned in the posting; they are transitive
    prerequisites the graph knows about and a keyword list cannot.
    """
    path = await paths.for_job(user=current_user, job_id=job_id)
    return LearningPathResponse(
        steps=_steps(path),
        step_count=path.step_count,
        total_effort=path.total_effort,
        unreachable=list(path.unreachable),
    )


@router.get(
    "/skills/{skill_id}/learning-path",
    response_model=SkillPathResponse,
    tags=["learning-path"],
    summary="How to reach one specific skill",
    responses={404: {"description": "No such skill"}},
)
async def skill_learning_path(
    skill_id: uuid.UUID, current_user: CurrentUser, paths: LearningPathServiceDep
) -> SkillPathResponse:
    """The full plan for one skill, plus the cheapest single route to it."""
    path, route = await paths.for_skill(user=current_user, skill_id=skill_id)
    return SkillPathResponse(
        steps=_steps(path),
        step_count=path.step_count,
        total_effort=path.total_effort,
        unreachable=list(path.unreachable),
        shortest_route=list(route),
    )
