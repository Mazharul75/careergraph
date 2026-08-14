"""Skill vocabulary and profile routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, SkillProfileServiceDep
from app.schemas.skill import (
    AddSkillRequest,
    SkillProfileResponse,
    SkillResponse,
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
    category: str | None = Query(default=None, description="Filter by category"),
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
    confirmed, suggested = await profile.get_profile(user_id=current_user.id)
    return SkillProfileResponse(
        confirmed=[UserSkillResponse.model_validate(e) for e in confirmed],
        suggested=[UserSkillResponse.model_validate(e) for e in suggested],
        total_confirmed=len(confirmed),
        total_suggested=len(suggested),
    )


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
