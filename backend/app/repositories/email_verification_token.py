"""Email verification token data access."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update

from app.models.email_verification_token import EmailVerificationToken
from app.repositories.base import BaseRepository


class EmailVerificationTokenRepository(BaseRepository[EmailVerificationToken]):
    model = EmailVerificationToken

    async def get_by_hash(self, token_hash: str) -> EmailVerificationToken | None:
        stmt = select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def invalidate_active_for_user(self, user_id: uuid.UUID, used_at: datetime) -> int:
        """Burn every unused token for a user in one statement.

        Called right before issuing a new one, on registration and on resend. Without this, a
        forgotten earlier email keeps working forever — resending a link should mean exactly
        one link is live, not two.
        """
        stmt = (
            update(EmailVerificationToken)
            .where(EmailVerificationToken.user_id == user_id)
            .where(EmailVerificationToken.used_at.is_(None))
            .values(used_at=used_at)
        )
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        return result.rowcount or 0
