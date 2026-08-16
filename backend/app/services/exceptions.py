"""Domain exceptions.

Services raise these. They carry no HTTP status codes and no ``Response`` objects, because a
service must not know it is being called over HTTP — the same ``AuthService`` will be called
from a Celery task later. Translation to status codes happens once, in ``app/api/errors.py``.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for expected, business-rule failures.

    Distinct from a bug. A ``DomainError`` means the request was well-formed but not permitted;
    anything else escaping a service is genuinely unexpected and should surface as a 500.
    """

    message = "The request could not be completed."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message


class EmailAlreadyRegisteredError(DomainError):
    message = "An account with this email already exists."


class InvalidCredentialsError(DomainError):
    """Wrong password, or no such account.

    One exception covers both cases deliberately. Separate errors would let anyone discover
    which addresses are registered by reading the error message.
    """

    message = "Incorrect email or password."


class InactiveAccountError(DomainError):
    message = "This account has been deactivated."


class InvalidRefreshTokenError(DomainError):
    message = "Refresh token is invalid or has expired."


class UnsupportedFileTypeError(DomainError):
    message = "Only PDF and DOCX files are supported."


class FileTooLargeError(DomainError):
    message = "File is too large."


class EmptyFileError(DomainError):
    message = "The uploaded file is empty."


class JobNotFoundError(DomainError):
    """Also raised for a private job belonging to someone else.

    One error for both, so job ids cannot be enumerated.
    """

    message = "Job not found."


class NotYourJobError(DomainError):
    message = "You can only modify jobs you created."


class RecruiterRoleRequiredError(DomainError):
    message = "Only recruiter accounts can publish public job postings."


class ActiveGoalExistsError(DomainError):
    """One target at a time.

    Not a technical limit — a product decision. The whole value of a goal is that it focuses
    attention; a user tracking six targets at once is back to an unordered pile.
    """

    message = "You already have an active goal. Complete or abandon it before setting another."


class GoalNotFoundError(DomainError):
    """Also raised for a goal belonging to someone else, so ids cannot be enumerated."""

    message = "Goal not found."


class GoalNotAchievedError(DomainError):
    message = "You have not reached this goal yet. Keep going."


class SkillNotFoundError(DomainError):
    message = "No such skill."


class SkillNotInProfileError(DomainError):
    message = "That skill is not in your profile."


class ResumeNotFoundError(DomainError):
    """Also raised when the resume exists but belongs to someone else.

    One error for both cases on purpose. A distinct "forbidden" would confirm that a given id
    exists, letting anyone enumerate how many resumes the system holds.
    """

    message = "Resume not found."


class TooManyPendingResumesError(DomainError):
    message = "You already have resumes waiting to be processed. Please wait for them to finish."


class RefreshTokenReuseDetectedError(DomainError):
    """An already-spent refresh token was presented again.

    Refresh tokens are single-use. Seeing one twice has exactly one explanation: a copy exists
    somewhere it should not. The entire token family is revoked in response.
    """

    message = "Session revoked for security reasons. Please sign in again."
