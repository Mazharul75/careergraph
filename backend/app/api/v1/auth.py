"""Authentication routes.

Every handler here does the same four things and nothing else: accept a validated schema, call
a service, shape the response, return it. No password is compared, no token is minted, and no
query is written in this file — that logic lives in ``app/services/auth.py`` and is unit-tested
without HTTP.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import AuthServiceDep, CurrentUser
from app.api.rate_limit import rate_limit
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserResponse,
)

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    responses={
        409: {"description": "Email already registered"},
        429: {"description": "Rate limit exceeded"},
    },
    # In `dependencies=` rather than the signature: the limiter yields no value the handler
    # needs, it either passes or raises. All three credential endpoints are limited per-IP —
    # they are unauthenticated, so they are the free attack surface. See ADR-0011.
    dependencies=[Depends(rate_limit("register"))],
)
async def register(payload: RegisterRequest, auth: AuthServiceDep) -> UserResponse:
    user = await auth.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
    )
    # Registration deliberately does not return tokens. Signing in is a separate, explicit act,
    # and keeping them apart means the login path — the one that must be constant-time and will
    # be rate-limited in Phase 5 — has exactly one entry point.
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Exchange credentials for a token pair",
    responses={
        401: {"description": "Incorrect email or password"},
        429: {"description": "Rate limit exceeded"},
    },
    dependencies=[Depends(rate_limit("login"))],
)
async def login(payload: LoginRequest, auth: AuthServiceDep) -> TokenPair:
    _user, tokens = await auth.login(email=payload.email, password=payload.password)
    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate a refresh token for a new pair",
    responses={
        401: {"description": "Token invalid, expired, or already used"},
        429: {"description": "Rate limit exceeded"},
    },
    dependencies=[Depends(rate_limit("refresh"))],
)
async def refresh(payload: RefreshRequest, auth: AuthServiceDep) -> TokenPair:
    tokens = await auth.refresh(raw_refresh_token=payload.refresh_token)
    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a session",
)
async def logout(payload: LogoutRequest, auth: AuthServiceDep) -> None:
    # Unauthenticated on purpose. A user whose access token has already expired must still be
    # able to end their session, and the refresh token itself is the proof of ownership.
    # Idempotent: an unknown token returns 204 rather than confirming it does not exist.
    await auth.logout(raw_refresh_token=payload.refresh_token)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="The authenticated user",
    responses={401: {"description": "Missing or invalid access token"}},
)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
