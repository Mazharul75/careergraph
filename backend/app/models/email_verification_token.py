"""Email verification token — the server-side half of confirming an address."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EmailVerificationToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One emailed link.

    Shaped like ``RefreshToken`` on purpose — both are "a random secret, hashed at rest,
    single-use, with an expiry." Unlike a refresh token, a spent verification link has no
    theft-detection value (there is nothing further to protect once the address is
    confirmed), so used rows are informational rather than a security tripwire.
    """

    __tablename__ = "email_verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SHA-256 hex digest, never the token itself — see app/core/security.py.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Null while live. Set on successful verification, and also set (without verifying
    # anything) when a newer token is issued for the same user — a resend must invalidate
    # whatever was emailed before it, or an old, already-forgotten link would still work.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at

    def is_usable(self, *, now: datetime | None = None) -> bool:
        return self.used_at is None and not self.is_expired(now=now)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = "used" if self.used_at else "active"
        return f"<EmailVerificationToken user={self.user_id} {state}>"
