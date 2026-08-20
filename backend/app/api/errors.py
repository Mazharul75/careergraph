"""Translation from domain errors to HTTP responses.

Registered once on the application. Services raise domain exceptions that know nothing about
HTTP; this is the single place those become status codes. The alternative — try/except in every
route handler — puts business-rule knowledge back into the HTTP layer and guarantees two
handlers eventually disagree about what status a given failure deserves.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    ActiveGoalExistsError,
    CannotDemoteLastAdminError,
    CannotSuspendYourselfError,
    DomainError,
    EmailAlreadyRegisteredError,
    EmptyFileError,
    FileTooLargeError,
    GoalNotAchievedError,
    GoalNotFoundError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    JobNotFoundError,
    NotYourJobError,
    RecruiterRoleRequiredError,
    RefreshTokenReuseDetectedError,
    ResumeNotFoundError,
    SkillNotFoundError,
    SkillNotInProfileError,
    TooManyPendingResumesError,
    UnsupportedFileTypeError,
    UserNotFoundError,
)
from app.services.extraction import ExtractionError

# 409 Conflict for a duplicate address; 401 for anything credential-related.
#
# Reuse detection returns 401 rather than a distinctive code on purpose: telling a client
# "reuse detected" confirms to an attacker that their stolen token was live and that the
# system noticed. The user-facing message says the session ended; the server-side log is where
# the security signal belongs.
_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    EmailAlreadyRegisteredError: status.HTTP_409_CONFLICT,
    InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    InactiveAccountError: status.HTTP_403_FORBIDDEN,
    InvalidRefreshTokenError: status.HTTP_401_UNAUTHORIZED,
    RefreshTokenReuseDetectedError: status.HTTP_401_UNAUTHORIZED,
    # --- Resumes ---
    # 400 for a request that is simply wrong, 409 for one that is well-formed but conflicts
    # with the account's current state, 404 for anything the caller may not see.
    EmptyFileError: status.HTTP_400_BAD_REQUEST,
    UnsupportedFileTypeError: status.HTTP_400_BAD_REQUEST,
    # 413 rather than 400: the request is valid in shape, the payload is simply too big, and
    # 413 is the status a client can act on programmatically.
    FileTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    ResumeNotFoundError: status.HTTP_404_NOT_FOUND,
    TooManyPendingResumesError: status.HTTP_409_CONFLICT,
    # --- Skills ---
    SkillNotFoundError: status.HTTP_404_NOT_FOUND,
    SkillNotInProfileError: status.HTTP_404_NOT_FOUND,
    # --- Jobs ---
    JobNotFoundError: status.HTTP_404_NOT_FOUND,
    NotYourJobError: status.HTTP_404_NOT_FOUND,
    RecruiterRoleRequiredError: status.HTTP_403_FORBIDDEN,
    # --- Goals ---
    GoalNotFoundError: status.HTTP_404_NOT_FOUND,
    # 409, not 400: the request is perfectly valid, it just conflicts with state that already
    # exists. The client's fix is to abandon the current goal, not to correct its payload.
    ActiveGoalExistsError: status.HTTP_409_CONFLICT,
    GoalNotAchievedError: status.HTTP_409_CONFLICT,
    # --- Admin ---
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    CannotSuspendYourselfError: status.HTTP_409_CONFLICT,
    CannotDemoteLastAdminError: status.HTTP_409_CONFLICT,
}

_AUTH_STATUSES = {status.HTTP_401_UNAUTHORIZED}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ExtractionError)
    async def _handle_extraction_error(_request: Request, exc: ExtractionError) -> JSONResponse:
        """Raised when a file's actual bytes are not a document we can read.

        Separate from DomainError because extraction is a pure module with no knowledge of the
        service layer. It surfaces at upload time when magic-byte detection rejects a file
        whose Content-Type claimed otherwise, so 400 is the right answer: the client sent
        something invalid.
        """
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    async def _handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        status_code = _STATUS_BY_ERROR.get(type(exc), status.HTTP_400_BAD_REQUEST)
        headers = {"WWW-Authenticate": "Bearer"} if status_code in _AUTH_STATUSES else None
        return JSONResponse(
            status_code=status_code,
            content={"detail": exc.message},
            headers=headers,
        )
