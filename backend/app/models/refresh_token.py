"""Refresh token model — the server-side half of token rotation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RefreshToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One issued refresh token.

    Rows are never deleted on use. A used token is marked revoked and kept, because detecting
    that an *already-spent* token has been presented again is the entire mechanism by which
    theft is discovered. Deleting spent rows would make a replayed token indistinguishable from
    one that never existed.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        # Deleting a user removes their tokens. Unlike resumes, a token has no value worth
        # preserving and an orphaned credential is a liability.
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SHA-256 hex digest, never the token itself — see app/core/security.py.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Every token descended from one login shares a family_id. When a spent token is replayed,
    # the whole family is revoked at once: the thief is ejected, and so is the legitimate user,
    # who then re-authenticates. Without this grouping there would be no way to answer "which
    # other tokens came from the session that was compromised?"
    family_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Null while the token is live. Set on rotation, on logout, and on family revocation.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Forms the rotation chain, so an incident can be traced from any link.
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at

    def is_usable(self, *, now: datetime | None = None) -> bool:
        return not self.is_revoked and not self.is_expired(now=now)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = "revoked" if self.is_revoked else "active"
        return f"<RefreshToken id={self.id} user={self.user_id} {state}>"
