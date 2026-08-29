"""User account model."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(enum.StrEnum):
    """Authorization role.

    ``StrEnum`` (Python 3.11+) is the supported form of the old ``class X(str, Enum)`` idiom:
    members *are* strings, so they serialise straight to JSON and compare cleanly against
    string literals, while still being a real enum for exhaustiveness checking.
    """

    JOB_SEEKER = "job_seeker"
    RECRUITER = "recruiter"
    # Operators. Never granted by registration or by any API call -- only by
    # scripts/promote_admin.py, run deliberately against the database.
    ADMIN = "admin"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A registered account.

    Note what is *absent*: no plaintext password column exists, anywhere, ever. The only
    credential stored is an Argon2 hash, written in Phase 1b.
    """

    __tablename__ = "users"

    # 320 is the RFC 5321 maximum for an email address (64 local + @ + 255 domain).
    # Addresses are normalised to lowercase before insert; the unique constraint is what makes
    # "one account per address" a database guarantee rather than an application hope.
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)

    # Nullable, deliberately: an account created through Google Sign-In has no password at
    # all, not an unusable placeholder one. `AuthService.login` treats a null hash as "this
    # account cannot authenticate by password" and refuses with the same generic error used
    # for a wrong password, so the distinction never leaks to a caller.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Null until the address is confirmed. Set by clicking an emailed link, or immediately at
    # creation for a Google account — Google has already proven mailbox ownership, so making
    # the user repeat that proof would be friction with no security benefit.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Google's stable, unique subject identifier for the account (the `sub` claim of its ID
    # tokens). Never the email address: a person can change the email tied to a Google
    # account, and `sub` is the one value guaranteed to keep pointing at the same identity.
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
            validate_strings=True,
            # By default SQLAlchemy stores the enum *member name* ("JOB_SEEKER"), not its
            # value ("job_seeker"). The API contract, the migration, and the database type all
            # use the lowercase value, so without this the ORM writes a label the PostgreSQL
            # type has never heard of.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=UserRole.JOB_SEEKER.value,
    )

    # Deactivation instead of deletion. Hard-deleting a user would cascade away their resumes
    # and match history, which is unrecoverable if the deletion was a mistake.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        # Defence in depth: the application lowercases addresses, and the database refuses the
        # row if it ever forgets. Without this, "A@x.com" and "a@x.com" become two accounts.
        CheckConstraint("email = lower(email)", name="email_is_lowercase"),
    )

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def has_password(self) -> bool:
        """Whether this account can authenticate with a password at all.

        False for a Google-only account. Exists as a named property rather than an inline
        ``is not None`` check so every call site reads as an intent, not an implementation
        detail of how OAuth-only accounts happen to be represented.
        """
        return self.password_hash is not None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id} email={self.email!r} role={self.role.value}>"
