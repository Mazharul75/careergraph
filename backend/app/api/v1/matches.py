"""Match scoring routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, MatchServiceDep
from app.schemas.match import MatchResponse, SkillGapResponse

router = APIRouter()


@router.get(
    "/{job_id}/match",
    response_model=MatchResponse,
    summary="Score your profile against a job",
    responses={404: {"description": "No such job, or it is private and not yours"}},
)
async def get_match(
    job_id: uuid.UUID, current_user: CurrentUser, matches: MatchServiceDep
) -> MatchResponse:
    """Combines skill coverage with semantic similarity, and shows its working.

    Answers immediately even when embeddings are not ready: `semantic_available` reports
    whether the semantic component contributed, so a client can explain a score that will
    change rather than appearing to contradict itself after a refresh.
    """
    result, semantic_available = await matches.score(user=current_user, job_id=job_id)

    return MatchResponse(
        job_id=job_id,
        score=result.score,
        skill_coverage=result.skill_coverage,
        semantic_similarity=result.semantic_similarity,
        semantic_available=semantic_available,
        matched=[
            SkillGapResponse(
                skill_id=g.skill_id, canonical_name=g.canonical_name, importance=g.importance
            )
            for g in result.matched
        ],
        missing=[
            SkillGapResponse(
                skill_id=g.skill_id, canonical_name=g.canonical_name, importance=g.importance
            )
            for g in result.missing
        ],
        total_required=result.total_required,
    )
