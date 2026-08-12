"""Resume routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import CurrentUser, ResumeServiceDep
from app.core.config import get_settings
from app.schemas.resume import ResumeSummary, ResumeText
from app.services.exceptions import FileTooLargeError

router = APIRouter()


@router.post(
    "",
    response_model=ResumeSummary,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a resume for background parsing",
    responses={
        202: {"description": "Accepted and queued; poll for status"},
        400: {"description": "Empty, oversized, or unsupported file"},
        409: {"description": "Too many resumes already awaiting processing"},
    },
)
async def upload_resume(
    current_user: CurrentUser,
    resumes: ResumeServiceDep,
    file: UploadFile = File(..., description="PDF or DOCX, max 5 MB"),
) -> ResumeSummary:
    """Accept a resume and return immediately.

    **202, not 201.** The resource exists, but the thing the client actually wants — parsed
    text — does not yet. 202 says "accepted, not finished", which is exactly the contract, and
    it tells the client to poll rather than assume the work is done.
    """
    settings = get_settings()

    # Read with a hard cap rather than `await file.read()`. An unbounded read pulls the entire
    # upload into memory before any size check runs, so a 2 GB request would OOM the process
    # regardless of the limit we intended to enforce. Reading one byte past the limit is enough
    # to know it is too big.
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise FileTooLargeError(
            f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit."
        )

    resume = await resumes.upload(
        user_id=current_user.id,
        filename=file.filename or "resume",
        content_type=file.content_type or "",
        data=data,
    )
    return ResumeSummary.model_validate(resume)


@router.get(
    "",
    response_model=list[ResumeSummary],
    summary="List your resumes",
)
async def list_resumes(current_user: CurrentUser, resumes: ResumeServiceDep) -> list[ResumeSummary]:
    records = await resumes.list_for_user(user_id=current_user.id)
    return [ResumeSummary.model_validate(record) for record in records]


@router.get(
    "/{resume_id}",
    response_model=ResumeSummary,
    summary="Check parse status",
    responses={404: {"description": "No such resume for this user"}},
)
async def get_resume(
    resume_id: uuid.UUID,
    current_user: CurrentUser,
    resumes: ResumeServiceDep,
) -> ResumeSummary:
    """Poll this until ``status`` is ``complete`` or ``failed``."""
    resume = await resumes.get(resume_id=resume_id, user_id=current_user.id)
    return ResumeSummary.model_validate(resume)


@router.get(
    "/{resume_id}/text",
    response_model=ResumeText,
    summary="Fetch the extracted text",
    responses={404: {"description": "No such resume for this user"}},
)
async def get_resume_text(
    resume_id: uuid.UUID,
    current_user: CurrentUser,
    resumes: ResumeServiceDep,
) -> ResumeText:
    """A separate endpoint from the status check, because the text can be large.

    Polling for status should stay cheap; nobody wants to re-download the full document body
    every two seconds while waiting.
    """
    resume = await resumes.get_text(resume_id=resume_id, user_id=current_user.id)
    return ResumeText(
        id=resume.id,
        status=resume.status,
        extracted_text=resume.extracted_text,
        character_count=len(resume.extracted_text or ""),
    )
