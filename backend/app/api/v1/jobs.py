"""Job routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, JobServiceDep
from app.schemas.job import (
    CreateJobRequest,
    JobResponse,
    JobSummary,
    UpdateJobRequest,
)

router = APIRouter()


def _summary(job: object) -> JobSummary:
    summary = JobSummary.model_validate(job)
    summary.skill_count = len(job.required_skills)  # type: ignore[attr-defined]
    return summary


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a job description",
    responses={403: {"description": "Only recruiters may publish public postings"}},
)
async def create_job(
    payload: CreateJobRequest, current_user: CurrentUser, jobs: JobServiceDep
) -> JobResponse:
    """201, not 202 — unlike resume upload.

    Skill extraction runs inline because matching a compiled vocabulary against pasted text
    takes milliseconds. The queue is for slow work, not for anything that happens to be
    derived. The job is complete and usable when this returns.
    """
    job = await jobs.create(
        user=current_user,
        title=payload.title,
        description=payload.description,
        company=payload.company,
        location=payload.location,
        is_public=payload.is_public,
    )
    return JobResponse.model_validate(job)


@router.get("", response_model=list[JobSummary], summary="Your jobs plus public postings")
async def list_jobs(current_user: CurrentUser, jobs: JobServiceDep) -> list[JobSummary]:
    return [_summary(job) for job in await jobs.list_visible(user=current_user)]


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="A job with its required skills",
    responses={404: {"description": "No such job, or it is private and not yours"}},
)
async def get_job(job_id: uuid.UUID, current_user: CurrentUser, jobs: JobServiceDep) -> JobResponse:
    return JobResponse.model_validate(await jobs.get(job_id=job_id, user=current_user))


@router.patch(
    "/{job_id}",
    response_model=JobResponse,
    summary="Edit a job you own",
    responses={404: {"description": "Not your job"}},
)
async def update_job(
    job_id: uuid.UUID,
    payload: UpdateJobRequest,
    current_user: CurrentUser,
    jobs: JobServiceDep,
) -> JobResponse:
    job = await jobs.update(
        job_id=job_id,
        user=current_user,
        title=payload.title,
        description=payload.description,
        company=payload.company,
        location=payload.location,
    )
    return JobResponse.model_validate(job)


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a job you own",
    responses={404: {"description": "Not your job"}},
)
async def delete_job(job_id: uuid.UUID, current_user: CurrentUser, jobs: JobServiceDep) -> None:
    await jobs.delete(job_id=job_id, user=current_user)
