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
    DomainError,
    EmailAlreadyRegisteredError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RefreshTokenReuseDetectedError,
)

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
}

_AUTH_STATUSES = {status.HTTP_401_UNAUTHORIZED}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        status_code = _STATUS_BY_ERROR.get(type(exc), status.HTTP_400_BAD_REQUEST)
        headers = {"WWW-Authenticate": "Bearer"} if status_code in _AUTH_STATUSES else None
        return JSONResponse(
            status_code=status_code,
            content={"detail": exc.message},
            headers=headers,
        )
