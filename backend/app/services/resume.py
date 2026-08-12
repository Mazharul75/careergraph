"""Resume upload and retrieval logic.

Like ``AuthService``, this imports no FastAPI and no SQLAlchemy — only repository protocols and
pure helpers. It is unit-tested against in-memory fakes and a recording dispatcher.
"""

from __future__ import annotations

import uuid

from app.models.resume import ParseStatus, Resume
from app.repositories.protocols import ResumeRepositoryProtocol, TaskDispatcher, UnitOfWork
from app.services.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    ResumeNotFoundError,
    TooManyPendingResumesError,
    UnsupportedFileTypeError,
)
from app.services.extraction import DOCX_CONTENT_TYPE, PDF_CONTENT_TYPE, detect_kind

ALLOWED_CONTENT_TYPES = frozenset({PDF_CONTENT_TYPE, DOCX_CONTENT_TYPE})

# One account cannot queue more than this many unprocessed resumes at once. With a single
# worker on free hosting, an unbounded queue means one user can delay everyone else
# indefinitely. This is not a substitute for rate limiting (Phase 5) — it is a fairness bound
# on a shared, scarce resource.
MAX_PENDING_PER_USER = 3


class ResumeService:
    def __init__(
        self,
        *,
        resumes: ResumeRepositoryProtocol,
        dispatcher: TaskDispatcher,
        uow: UnitOfWork,
        max_upload_bytes: int,
    ) -> None:
        self._resumes = resumes
        self._dispatcher = dispatcher
        self._uow = uow
        self._max_upload_bytes = max_upload_bytes

    async def upload(
        self,
        *,
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> Resume:
        """Accept a resume and queue it for parsing.

        Returns as soon as the row is committed and the message is published. No parsing
        happens here — that is the entire point of the queue.
        """
        if not data:
            raise EmptyFileError

        if len(data) > self._max_upload_bytes:
            raise FileTooLargeError(
                f"File exceeds the {self._max_upload_bytes // (1024 * 1024)} MB limit."
            )

        # Two independent checks, and both are needed.
        #
        # Content-Type is chosen by the client and can claim anything, so it is a convenience
        # check, not a control. `detect_kind` reads the file's magic bytes, which the client
        # cannot forge without actually supplying a file of that type.
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise UnsupportedFileTypeError
        detect_kind(data)  # raises ExtractionError if the bytes disagree with the claim

        if await self._resumes.count_pending_for_user(user_id) >= MAX_PENDING_PER_USER:
            raise TooManyPendingResumesError

        resume = Resume(
            user_id=user_id,
            original_filename=_safe_filename(filename),
            content_type=content_type,
            size_bytes=len(data),
            file_data=data,
            status=ParseStatus.PENDING,
        )
        self._resumes.add(resume)

        # Commit *before* enqueuing. If the order were reversed, a fast worker could pick up
        # the message and query for a row that has not been committed yet — a race that shows
        # up as intermittent "resume no longer exists" failures under load.
        #
        # The remaining risk is the opposite one: committed but never enqueued, if the process
        # dies in between. That leaves a resume stuck in `pending`, which is recoverable by a
        # sweeper (Phase 6) — far better than losing the upload entirely.
        await self._uow.commit()
        self._dispatcher.enqueue_resume_parse(resume.id)

        return resume

    async def get(self, *, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume:
        resume = await self._resumes.get_for_user(resume_id, user_id)
        if resume is None:
            # Same error whether it does not exist or belongs to someone else — see
            # ResumeNotFoundError.
            raise ResumeNotFoundError
        return resume

    async def get_text(self, *, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume:
        resume = await self._resumes.get_with_text(resume_id, user_id)
        if resume is None:
            raise ResumeNotFoundError
        return resume

    async def list_for_user(self, *, user_id: uuid.UUID, limit: int = 50) -> list[Resume]:
        return await self._resumes.list_for_user(user_id, limit=limit)


def _safe_filename(filename: str) -> str:
    """Reduce a client-supplied filename to something safe to store and echo back.

    The name is never used as a filesystem path — the bytes go into Postgres — but it *is*
    returned in API responses and will be rendered in the UI. Stripping directory components
    and control characters removes both the traversal shape and the injection shape.
    """
    cleaned = filename.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(ch for ch in cleaned if ch.isprintable() and ch not in '<>:"|?*')
    cleaned = cleaned.strip() or "resume"
    return cleaned[:255]
