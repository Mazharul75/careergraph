"""Authentication request and response contracts."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole

# Minimum 12 characters, no composition rules. NIST SP 800-63B explicitly recommends length
# over forced complexity: "P@ssw0rd!" satisfies every classic rule and is trivially cracked,
# while a long passphrase is both stronger and easier to remember.
#
# The maximum is a denial-of-service guard, not a security property. Argon2 costs time and
# memory proportional to input, so an unbounded field lets one request tie up a worker.
Password = Annotated[str, Field(min_length=12, max_length=128)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Password
    full_name: str | None = Field(default=None, max_length=200)
    # Literal, not UserRole. This is the single line that stops anyone registering themselves
    # as an admin: the enum has an ADMIN member, and accepting the bare enum here would let a
    # crafted signup request claim it. Privilege is granted only by scripts/promote_admin.py.
    role: Literal[UserRole.JOB_SEEKER, UserRole.RECRUITER] = UserRole.JOB_SEEKER

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        # Normalised at the boundary so nothing downstream has to remember to. The matching
        # CHECK constraint on the column is the backstop if something ever does forget.
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def reject_whitespace_only_padding(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password cannot be entirely whitespace.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class TokenPair(BaseModel):
    """Issued on login and on every refresh.

    ``refresh_token`` appears here exactly once and is never retrievable again — only its hash
    is stored server-side.
    """

    access_token: str
    refresh_token: str
    # The literal "bearer" is the RFC 6750 scheme name, not a credential. Ruff's
    # hardcoded-password check (S105) fires on any assignment whose name contains "token".
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int = Field(description="Access token lifetime in seconds.")


class UserResponse(BaseModel):
    """A user as the API exposes them.

    Separate from the ORM model on purpose. ``password_hash`` is not a field here, so it cannot
    leak into a response even if someone adds a careless ``return user``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: UserRole
    is_active: bool
    email_verified: bool
    # Whether this account can sign in with a password at all — false for a Google-only
    # account. Lets the frontend hide "change password" for an account that has none.
    has_password: bool


class RegisterResponse(UserResponse):
    """What ``POST /auth/register`` returns.

    ``dev_verification_token`` is the raw token that would otherwise only ever reach the user
    through an email — present only when ``Settings.exposes_dev_verification_tokens`` is true
    (local and CI), never in staging or production. See the field's own note in
    ``app/core/config.py``.
    """

    dev_verification_token: str | None = Field(
        default=None,
        description="Local/CI only. Lets tests and the demo seeder verify without an inbox.",
    )


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)


class ResendVerificationRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        return value.strip().lower()


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        return value.strip().lower()


class ForgotPasswordResponse(BaseModel):
    """Always the same shape, whether or not the address exists — see the route docstring."""

    dev_reset_token: str | None = Field(
        default=None,
        description="Local/CI only. Lets tests reset a password without an inbox.",
    )


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: Password


class GoogleAuthRequest(BaseModel):
    """The ID token Google Identity Services hands the frontend after a successful sign-in.

    Nothing else is accepted from the client — email, name, and account id are all read back
    out of the token itself once its signature is verified, never taken from the request body.
    A client-supplied email here would let anyone claim any address.
    """

    id_token: str = Field(min_length=1, max_length=4096)
