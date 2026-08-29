"""Shared FastAPI dependencies.

Dependency injection here means a route declares *what it needs* in its signature and FastAPI
supplies it. Nothing constructs its own database session, repository, or service, so a test can
swap any of them out through ``app.dependency_overrides`` without patching module globals.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import TokenError, decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.repositories.admin import AdminRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.career_goal import CareerGoalRepository
from app.repositories.email_verification_token import EmailVerificationTokenRepository
from app.repositories.job import JobRepository
from app.repositories.password_reset_token import PasswordResetTokenRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.resume import ResumeRepository
from app.repositories.skill import SkillRepository, UserSkillRepository
from app.repositories.user import UserRepository
from app.services.admin import AdminService
from app.services.auth import AuthService
from app.services.candidates import CandidateService
from app.services.email import EmailSenderProtocol, get_email_sender
from app.services.goal import GoalService
from app.services.google_auth import GoogleTokenVerifier, verify_google_id_token
from app.services.job import JobService
from app.services.learning_path import LearningPathService
from app.services.match import MatchService
from app.services.resume import ResumeService
from app.services.skill_profile import SkillProfileService
from app.workers.dispatcher import CeleryTaskDispatcher

# Annotated aliases keep route signatures readable. Without this, every handler needing a
# session repeats `session: AsyncSession = Depends(get_db)`.
DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_user_repository(session: DbSession) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repository(session: DbSession) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def get_email_verification_token_repository(
    session: DbSession,
) -> EmailVerificationTokenRepository:
    return EmailVerificationTokenRepository(session)


def get_password_reset_token_repository(session: DbSession) -> PasswordResetTokenRepository:
    return PasswordResetTokenRepository(session)


UserRepo = Annotated[UserRepository, Depends(get_user_repository)]
RefreshTokenRepo = Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)]
EmailVerificationTokenRepo = Annotated[
    EmailVerificationTokenRepository, Depends(get_email_verification_token_repository)
]
PasswordResetTokenRepo = Annotated[
    PasswordResetTokenRepository, Depends(get_password_reset_token_repository)
]


def get_email_sender_dep() -> EmailSenderProtocol:
    """A dependency wrapper around ``get_email_sender`` so tests can override delivery
    (via ``app.dependency_overrides``) without touching ``RESEND_API_KEY``."""
    return get_email_sender()


EmailSenderDep = Annotated[EmailSenderProtocol, Depends(get_email_sender_dep)]


def get_google_verifier() -> GoogleTokenVerifier:
    """The real, PyJWT-backed Google ID token verifier.

    A dependency rather than a hardcoded default, so an integration test can override it
    through ``app.dependency_overrides`` — the same seam ``get_task_dispatcher`` uses — and
    exercise the whole account-creation/linking flow with a fake identity, no real Google
    credentials or network access required.
    """
    return verify_google_id_token


GoogleVerifierDep = Annotated[GoogleTokenVerifier, Depends(get_google_verifier)]


def get_auth_service(
    session: DbSession,
    users: UserRepo,
    refresh_tokens: RefreshTokenRepo,
    email_tokens: EmailVerificationTokenRepo,
    password_reset_tokens: PasswordResetTokenRepo,
    email_sender: EmailSenderDep,
    google_verifier: GoogleVerifierDep,
) -> AuthService:
    """Assemble AuthService from its collaborators.

    The session is passed as the unit of work. ``AsyncSession`` structurally satisfies the
    ``UnitOfWork`` protocol, so the service sees only ``commit`` and ``flush`` — it cannot
    reach around the repositories and execute its own SQL.
    """
    return AuthService(
        users=users,
        refresh_tokens=refresh_tokens,
        email_tokens=email_tokens,
        password_reset_tokens=password_reset_tokens,
        email_sender=email_sender,
        uow=session,
        google_verifier=google_verifier,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_resume_repository(session: DbSession) -> ResumeRepository:
    return ResumeRepository(session)


ResumeRepo = Annotated[ResumeRepository, Depends(get_resume_repository)]


def get_task_dispatcher() -> CeleryTaskDispatcher:
    """The real queue publisher.

    A dependency rather than a direct import inside the service, so integration tests can
    override it with a recorder and assert on enqueue behaviour without running a broker.
    """
    return CeleryTaskDispatcher()


TaskDispatcherDep = Annotated[CeleryTaskDispatcher, Depends(get_task_dispatcher)]


def get_resume_service(
    session: DbSession,
    resumes: ResumeRepo,
    dispatcher: TaskDispatcherDep,
) -> ResumeService:
    return ResumeService(
        resumes=resumes,
        dispatcher=dispatcher,
        uow=session,
        max_upload_bytes=get_settings().max_upload_bytes,
    )


ResumeServiceDep = Annotated[ResumeService, Depends(get_resume_service)]


def get_skill_repository(session: DbSession) -> SkillRepository:
    return SkillRepository(session)


def get_user_skill_repository(session: DbSession) -> UserSkillRepository:
    return UserSkillRepository(session)


def get_skill_profile_service(
    session: DbSession,
    skills: Annotated[SkillRepository, Depends(get_skill_repository)],
    user_skills: Annotated[UserSkillRepository, Depends(get_user_skill_repository)],
) -> SkillProfileService:
    return SkillProfileService(skills=skills, user_skills=user_skills, uow=session)


SkillProfileServiceDep = Annotated[SkillProfileService, Depends(get_skill_profile_service)]


def get_job_repository(session: DbSession) -> JobRepository:
    return JobRepository(session)


def get_job_service(
    session: DbSession,
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    skills: Annotated[SkillRepository, Depends(get_skill_repository)],
    dispatcher: TaskDispatcherDep,
) -> JobService:
    return JobService(jobs=jobs, skills=skills, dispatcher=dispatcher, uow=session)


JobServiceDep = Annotated[JobService, Depends(get_job_service)]


def get_match_service(
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    resumes: ResumeRepo,
    user_skills: Annotated[UserSkillRepository, Depends(get_user_skill_repository)],
) -> MatchService:
    return MatchService(jobs=jobs, resumes=resumes, user_skills=user_skills)


MatchServiceDep = Annotated[MatchService, Depends(get_match_service)]


def get_career_goal_repository(session: DbSession) -> CareerGoalRepository:
    return CareerGoalRepository(session)


def get_goal_service(
    session: DbSession,
    goals: Annotated[CareerGoalRepository, Depends(get_career_goal_repository)],
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    user_skills: Annotated[UserSkillRepository, Depends(get_user_skill_repository)],
    matcher: MatchServiceDep,
) -> GoalService:
    """Composed on top of MatchService rather than duplicating its scoring.

    A goal *is* a match measured twice, so re-deriving the score here would guarantee the two
    numbers eventually disagree — and a progress bar that contradicts the job page is worse
    than no progress bar.
    """
    return GoalService(
        goals=goals, jobs=jobs, user_skills=user_skills, matcher=matcher, uow=session
    )


GoalServiceDep = Annotated[GoalService, Depends(get_goal_service)]


def get_candidate_repository(session: DbSession) -> CandidateRepository:
    return CandidateRepository(session)


def get_candidate_service(
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    candidates: Annotated[CandidateRepository, Depends(get_candidate_repository)],
    resumes: ResumeRepo,
) -> CandidateService:
    return CandidateService(jobs=jobs, candidates=candidates, resumes=resumes)


CandidateServiceDep = Annotated[CandidateService, Depends(get_candidate_service)]


def get_admin_repository(session: DbSession) -> AdminRepository:
    return AdminRepository(session)


def get_admin_service(
    session: DbSession,
    admin_repo: Annotated[AdminRepository, Depends(get_admin_repository)],
    users: UserRepo,
) -> AdminService:
    return AdminService(admin_repo=admin_repo, users=users, uow=session)


AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]


def get_learning_path_service(
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    skills: Annotated[SkillRepository, Depends(get_skill_repository)],
    user_skills: Annotated[UserSkillRepository, Depends(get_user_skill_repository)],
) -> LearningPathService:
    return LearningPathService(jobs=jobs, skills=skills, user_skills=user_skills)


LearningPathServiceDep = Annotated[LearningPathService, Depends(get_learning_path_service)]


# --------------------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------------------

# auto_error=False so we raise our own 401 with a WWW-Authenticate header, instead of the
# 403 that Starlette's default returns for a missing Authorization header. A missing
# credential is "unauthenticated" (401), not "forbidden" (403) — the distinction tells a
# client whether to log in or give up.
_bearer_scheme = HTTPBearer(auto_error=False, description="Paste an access token from /auth/login")

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    users: UserRepo,
) -> User:
    """Resolve the caller from their bearer token.

    Every failure returns the same opaque 401. Distinguishing "expired" from "malformed" from
    "no such user" would tell an attacker which of their guesses was closest.
    """
    if credentials is None or not credentials.credentials:
        raise _UNAUTHENTICATED

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise _UNAUTHENTICATED from exc

    # The database is still consulted despite the token being self-describing. A JWT cannot be
    # revoked, so without this lookup a deactivated user would keep full access until their
    # token expired. One indexed primary-key read is a cheap price for that.
    user = await users.get(payload.user_id)
    if user is None or not user.is_active:
        raise _UNAUTHENTICATED

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*allowed: UserRole) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Build a dependency that admits only the listed roles.

    A factory rather than a fixed dependency so each route states its own requirement:
    ``Depends(require_role(UserRole.RECRUITER))``. Authorization stays declarative and visible
    in the signature, rather than buried in an ``if`` at the top of the handler where it is
    easy to forget.

    Returns 403, not 401: the caller proved who they are, they simply are not permitted.
    """

    async def _check(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return _check
