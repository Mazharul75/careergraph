"""Password reset token — the server-side half of "forgot your password"."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PasswordResetToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One emailed reset link.

    A separate table from ``EmailVerificationToken`` despite the identical shape, matching
    this codebase's existing choice to keep ``RefreshToken`` distinct from both rather than
    reusing one polymorphic "token" table with a purpose column. Each token type has its own
    lifetime — a reset link is deliberately much shorter-lived, because it grants control of
    the account outright rather than merely confirming an address — and its own blast radius
    if the table were ever compromised.
    """

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at

    def is_usable(self, *, now: datetime | None = None) -> bool:
        return self.used_at is None and not self.is_expired(now=now)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = "used" if self.used_at else "active"
        return f"<PasswordResetToken user={self.user_id} {state}>"
