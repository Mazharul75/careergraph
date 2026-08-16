"""Career goal routes — set a target, watch the score move, bank the win."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, GoalServiceDep
from app.schemas.goal import (
    AchievementResponse,
    GoalProgressResponse,
    GoalSkillGap,
    SetGoalRequest,
)
from app.schemas.job import JobSummary
from app.services.goal import GoalProgress

router = APIRouter()


def _to_response(progress: GoalProgress) -> GoalProgressResponse:
    """Flatten the service's dataclass into the wire contract.

    Done here rather than in the service because ``GoalProgress`` is deliberately free of
    Pydantic and HTTP concerns — it is the shape the business logic finds convenient, and
    unit tests build it by hand.
    """
    learning = set(progress.learning)
    return GoalProgressResponse(
        id=progress.goal.id,
        job=JobSummary.model_validate(progress.goal.job),
        created_at=progress.goal.created_at,
        achieved_at=progress.goal.achieved_at,
        baseline_score=progress.baseline_score,
        current_score=progress.current_score,
        delta=progress.delta,
        readiness=progress.readiness,
        is_achievable_now=progress.is_achievable_now,
        matched=[
            GoalSkillGap(
                skill_id=gap.skill_id,
                canonical_name=gap.canonical_name,
                importance=gap.importance,
                is_learning=gap.skill_id in learning,
            )
            for gap in progress.matched
        ],
        missing=[
            GoalSkillGap(
                skill_id=gap.skill_id,
                canonical_name=gap.canonical_name,
                importance=gap.importance,
                is_learning=gap.skill_id in learning,
            )
            for gap in progress.missing
        ],
        learning_count=len(progress.learning),
        semantic_available=progress.semantic_available,
    )


@router.post(
    "",
    response_model=GoalProgressResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Set a job as your target role",
    responses={
        404: {"description": "No such job, or it is not visible to you"},
        409: {"description": "You already have an active goal"},
    },
)
async def set_goal(
    payload: SetGoalRequest, current_user: CurrentUser, goals: GoalServiceDep
) -> GoalProgressResponse:
    """Adopt a job as the thing you are working toward.

    The match score at this instant is frozen as the baseline. It is the only moment it can
    be captured — a minute later the user's profile may have changed, and that change is
    exactly what the goal exists to measure.
    """
    return _to_response(await goals.set_goal(user=current_user, job_id=payload.job_id))


@router.get(
    "/current",
    response_model=GoalProgressResponse | None,
    summary="Your active goal and how far you have come",
)
async def get_current_goal(
    current_user: CurrentUser, goals: GoalServiceDep
) -> GoalProgressResponse | None:
    """Returns ``null`` rather than 404 when no goal is set.

    Having no goal is a normal state for a new account, not an error. A 404 would force the
    client to treat "you have not started yet" as a failure and litter the dashboard with
    error handling for the most common first-visit case.
    """
    progress = await goals.get_current(user=current_user)
    return _to_response(progress) if progress else None


@router.post(
    "/{goal_id}/achieve",
    response_model=AchievementResponse,
    summary="Bank a goal you have reached",
    responses={
        404: {"description": "No such goal, or it is already achieved"},
        409: {"description": "Your score has not reached the threshold yet"},
    },
)
async def achieve_goal(
    goal_id: uuid.UUID, current_user: CurrentUser, goals: GoalServiceDep
) -> AchievementResponse:
    """The server verifies the score rather than trusting the claim — an achievement anyone
    can award themselves is not an achievement."""
    goal = await goals.mark_achieved(user=current_user, goal_id=goal_id)
    return AchievementResponse.model_validate(goal)


@router.get(
    "/achievements",
    response_model=list[AchievementResponse],
    summary="Goals you have reached",
)
async def list_achievements(
    current_user: CurrentUser, goals: GoalServiceDep
) -> list[AchievementResponse]:
    return [
        AchievementResponse.model_validate(goal)
        for goal in await goals.list_achievements(user=current_user)
    ]


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Abandon an active goal",
    responses={404: {"description": "No such goal"}},
)
async def abandon_goal(
    goal_id: uuid.UUID, current_user: CurrentUser, goals: GoalServiceDep
) -> Response:
    await goals.abandon(user=current_user, goal_id=goal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
