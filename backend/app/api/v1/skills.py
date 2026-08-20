"""Skill vocabulary and profile routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, SkillProfileServiceDep
from app.schemas.skill import (
    AddSkillRequest,
    SkillEdgeResponse,
    SkillGraphResponse,
    SkillProfileResponse,
    SkillResponse,
    StartLearningRequest,
    UpdateSkillRequest,
    UserSkillResponse,
)

router = APIRouter()


@router.get(
    "",
    response_model=list[SkillResponse],
    summary="The full skill vocabulary",
)
async def list_skills(
    profile: SkillProfileServiceDep,
    # Bounded even though it is only compared for equality: this is an unauthenticated
    # endpoint, and "no input without a length limit" is cheaper as a blanket rule than as
    # a per-case judgement call.
    category: str | None = Query(default=None, max_length=50, description="Filter by category"),
) -> list[SkillResponse]:
    """Unauthenticated: the vocabulary is reference data, not user data.

    The frontend needs it to render an "add a skill" picker before the user has uploaded
    anything, and there is nothing private about the list of technologies that exist.
    """
    skills = await profile.list_vocabulary()
    if category:
        skills = [s for s in skills if s.category.value == category]
    return [SkillResponse.model_validate(skill) for skill in skills]


@router.get(
    "/graph",
    response_model=SkillGraphResponse,
    summary="The whole skill graph: vocabulary plus prerequisite edges",
)
async def get_skill_graph(profile: SkillProfileServiceDep) -> SkillGraphResponse:
    """Unauthenticated, like the vocabulary itself.

    Declared *before* `/me` and any `/{skill_id}` route: FastAPI matches in declaration
    order, so a literal path registered after a parameterised one would never be reached.
    """
    skills, edges = await profile.get_graph()
    return SkillGraphResponse(
        skills=[SkillResponse.model_validate(s) for s in skills],
        edges=[
            SkillEdgeResponse(prerequisite_id=prerequisite, skill_id=skill)
            for prerequisite, skill in edges
        ],
    )


@router.get(
    "/me",
    response_model=SkillProfileResponse,
    summary="Your skill profile",
)
async def get_my_profile(
    current_user: CurrentUser, profile: SkillProfileServiceDep
) -> SkillProfileResponse:
    """Confirmed and suggested skills, separately.

    The split is the point: suggestions are the extractor's guesses awaiting review, and
    keeping them apart from confirmed skills is what makes the correction step obvious rather
    than something the user has to go looking for.
    """
    confirmed, suggested, learning = await profile.get_profile(user_id=current_user.id)
    return SkillProfileResponse(
        confirmed=[UserSkillResponse.model_validate(e) for e in confirmed],
        suggested=[UserSkillResponse.model_validate(e) for e in suggested],
        learning=[UserSkillResponse.model_validate(e) for e in learning],
        total_confirmed=len(confirmed),
        total_suggested=len(suggested),
        total_learning=len(learning),
    )


@router.post(
    "/me/learning",
    response_model=UserSkillResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start learning a skill you do not have yet",
    responses={404: {"description": "No such skill in the vocabulary"}},
)
async def start_learning(
    payload: StartLearningRequest, current_user: CurrentUser, profile: SkillProfileServiceDep
) -> UserSkillResponse:
    """Begin working on a gap.

    Separate from ``POST /me`` because that one asserts "I already have this skill" and counts
    toward the match score immediately. This one asserts the opposite, and deliberately does
    **not** move the score — that only happens when the skill is later confirmed as learned.
    """
    entry = await profile.start_learning(user_id=current_user.id, skill_id=payload.skill_id)
    return UserSkillResponse.model_validate(entry)


@router.post(
    "/me",
    response_model=UserSkillResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a skill the extractor missed",
    responses={404: {"description": "No such skill in the vocabulary"}},
)
async def add_skill(
    payload: AddSkillRequest, current_user: CurrentUser, profile: SkillProfileServiceDep
) -> UserSkillResponse:
    entry = await profile.add_skill(
        user_id=current_user.id, skill_id=payload.skill_id, proficiency=payload.proficiency
    )
    return UserSkillResponse.model_validate(entry)


@router.patch(
    "/me/{skill_id}",
    response_model=UserSkillResponse,
    summary="Confirm, reject, or rate a skill",
    responses={404: {"description": "That skill is not in your profile"}},
)
async def update_skill(
    skill_id: uuid.UUID,
    payload: UpdateSkillRequest,
    current_user: CurrentUser,
    profile: SkillProfileServiceDep,
) -> UserSkillResponse:
    """PATCH, not PUT: a client confirming a skill should not have to send proficiency too."""
    entry = await profile.update_skill(
        user_id=current_user.id,
        skill_id=skill_id,
        status=payload.status,
        proficiency=payload.proficiency,
    )
    return UserSkillResponse.model_validate(entry)


@router.post(
    "/me/confirm-all",
    summary="Accept every outstanding suggestion",
)
async def confirm_all(current_user: CurrentUser, profile: SkillProfileServiceDep) -> dict[str, int]:
    confirmed = await profile.confirm_all_suggestions(user_id=current_user.id)
    return {"confirmed": confirmed}
