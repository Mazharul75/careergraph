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
from app.core.config import get_settings
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    GoogleAuthRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenPair,
    UserResponse,
    VerifyEmailRequest,
)

router = APIRouter()


@router.post(
    "/register",
    response_model=RegisterResponse,
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
async def register(payload: RegisterRequest, auth: AuthServiceDep) -> RegisterResponse:
    """Create an account and send a verification email.

    The account cannot sign in by password until that link is followed. Registration
    deliberately does not return tokens even so: signing in is a separate, explicit act, which
    keeps the login path — the one that must be constant-time and is separately rate-limited
    — as the single entry point for issuing a session.
    """
    user, raw_token = await auth.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
    )
    response = RegisterResponse.model_validate(user)
    if get_settings().exposes_dev_verification_tokens:
        response.dev_verification_token = raw_token
    return response


@router.post(
    "/verify-email",
    response_model=UserResponse,
    summary="Confirm an email address",
    responses={
        400: {"description": "Invalid or expired token"},
        429: {"description": "Rate limit exceeded"},
    },
    dependencies=[Depends(rate_limit("verify_email"))],
)
async def verify_email(payload: VerifyEmailRequest, auth: AuthServiceDep) -> UserResponse:
    user = await auth.verify_email(raw_token=payload.token)
    return UserResponse.model_validate(user)


@router.post(
    "/resend-verification",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Send a fresh verification link",
    responses={429: {"description": "Rate limit exceeded"}},
    dependencies=[Depends(rate_limit("resend_verification"))],
)
async def resend_verification(payload: ResendVerificationRequest, auth: AuthServiceDep) -> None:
    """Always 204, whether or not the address exists or was already verified.

    An endpoint that answers differently for "unverified" than for "no such account" is an
    enumeration oracle, and registration already accepts that trade-off once — there is no
    reason to add a second place where it leaks.
    """
    await auth.resend_verification(email=payload.email)


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Request a password reset link",
    responses={429: {"description": "Rate limit exceeded"}},
    dependencies=[Depends(rate_limit("forgot_password"))],
)
async def forgot_password(
    payload: ForgotPasswordRequest, auth: AuthServiceDep
) -> ForgotPasswordResponse:
    """Always 200 with the same shape, whether or not the address exists or has a password.

    Distinguishing those cases would tell an attacker which addresses are registered, and
    for a Google-only account, that they specifically have no password to attack — both are
    the same class of enumeration leak ``/auth/resend-verification`` is careful to avoid.
    """
    raw_token = await auth.request_password_reset(email=payload.email)
    exposed = raw_token if get_settings().exposes_dev_verification_tokens else None
    return ForgotPasswordResponse(dev_reset_token=exposed)


@router.post(
    "/reset-password",
    response_model=UserResponse,
    summary="Set a new password from a reset link",
    responses={
        400: {"description": "Invalid or expired token"},
        429: {"description": "Rate limit exceeded"},
    },
    dependencies=[Depends(rate_limit("reset_password"))],
)
async def reset_password(payload: ResetPasswordRequest, auth: AuthServiceDep) -> UserResponse:
    """Setting a new password revokes every existing session, on every device.

    A reset is often triggered *because* something was compromised, and leaving old sessions
    alive would let whoever had the old password — or a stolen token — keep going regardless
    of the new one.
    """
    user = await auth.reset_password(raw_token=payload.token, new_password=payload.new_password)
    return UserResponse.model_validate(user)


@router.post(
    "/google",
    response_model=TokenPair,
    summary="Sign in (or sign up) with a Google ID token",
    responses={
        401: {"description": "The Google ID token failed verification"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "Google Sign-In is not configured on this deployment"},
    },
    dependencies=[Depends(rate_limit("google_auth"))],
)
async def google_auth(payload: GoogleAuthRequest, auth: AuthServiceDep) -> TokenPair:
    _user, tokens = await auth.authenticate_with_google(id_token=payload.id_token)
    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Exchange credentials for a token pair",
    responses={
        401: {"description": "Incorrect email or password"},
        403: {"description": "Account deactivated or email not yet verified"},
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
