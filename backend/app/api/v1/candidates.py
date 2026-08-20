"""Recruiter-facing candidate ranking."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import CandidateServiceDep, CurrentUser, require_role
from app.models.user import UserRole
from app.schemas.candidate import RankedCandidateResponse
from app.schemas.goal import GoalSkillGap

router = APIRouter()


@router.get(
    "/{job_id}/candidates",
    response_model=list[RankedCandidateResponse],
    summary="Candidates ranked against your posting",
    dependencies=[Depends(require_role(UserRole.RECRUITER, UserRole.ADMIN))],
    responses={
        403: {"description": "Only recruiters can rank candidates"},
        404: {"description": "No such job, or you do not own it"},
    },
)
async def rank_candidates(
    job_id: uuid.UUID,
    current_user: CurrentUser,
    candidates: CandidateServiceDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RankedCandidateResponse]:
    """The recruiter half of the product: the same scoring engine, pointed the other way.

    Two guards, not one. The role check keeps job seekers out of the talent pool entirely;
    the ownership check inside the service stops a recruiter ranking candidates against
    somebody else's posting, which would otherwise turn any public job id into a directory
    of every candidate on the platform.
    """
    ranked = await candidates.rank_for_job(recruiter=current_user, job_id=job_id, limit=limit)
    return [
        RankedCandidateResponse(
            user_id=c.user_id,
            full_name=c.full_name,
            score=c.score,
            skill_coverage=c.skill_coverage,
            semantic_similarity=c.semantic_similarity,
            matched=[
                GoalSkillGap(
                    skill_id=g.skill_id,
                    canonical_name=g.canonical_name,
                    importance=g.importance,
                )
                for g in c.matched
            ],
            missing=[
                GoalSkillGap(
                    skill_id=g.skill_id,
                    canonical_name=g.canonical_name,
                    importance=g.importance,
                )
                for g in c.missing
            ],
            has_resume=c.has_resume,
        )
        for c in ranked
    ]
