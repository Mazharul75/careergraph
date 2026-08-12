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
