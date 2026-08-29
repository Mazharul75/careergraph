"""Password reset token data access."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update

from app.models.password_reset_token import PasswordResetToken
from app.repositories.base import BaseRepository


class PasswordResetTokenRepository(BaseRepository[PasswordResetToken]):
    model = PasswordResetToken

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def invalidate_active_for_user(self, user_id: uuid.UUID, used_at: datetime) -> int:
        """Burn every unused reset link for a user before issuing a new one.

        Same reasoning as the email-verification equivalent: a second "forgot password"
        click should mean exactly one live link, not two, and a real reset must retire the
        link that made it possible.
        """
        stmt = (
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id)
            .where(PasswordResetToken.used_at.is_(None))
            .values(used_at=used_at)
        )
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        return result.rowcount or 0
