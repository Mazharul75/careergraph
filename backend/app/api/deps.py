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

from app.core.security import TokenError, decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.services.auth import AuthService

# Annotated aliases keep route signatures readable. Without this, every handler needing a
# session repeats `session: AsyncSession = Depends(get_db)`.
DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_user_repository(session: DbSession) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repository(session: DbSession) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


UserRepo = Annotated[UserRepository, Depends(get_user_repository)]
RefreshTokenRepo = Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)]


def get_auth_service(
    session: DbSession,
    users: UserRepo,
    refresh_tokens: RefreshTokenRepo,
) -> AuthService:
    """Assemble AuthService from its collaborators.

    The session is passed as the unit of work. ``AsyncSession`` structurally satisfies the
    ``UnitOfWork`` protocol, so the service sees only ``commit`` and ``flush`` — it cannot
    reach around the repositories and execute its own SQL.
    """
    return AuthService(users=users, refresh_tokens=refresh_tokens, uow=session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


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
