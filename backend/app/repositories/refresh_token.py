"""Refresh token data access."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Find a token by its stored hash.

        Deliberately returns revoked and expired tokens too. The service has to be able to tell
        "this token was already spent" (theft) apart from "no such token" (garbage input), and
        filtering here would collapse those two cases into one.
        """
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_family(self, family_id: uuid.UUID, revoked_at: datetime) -> int:
        """Revoke every live token in a rotation chain. Returns how many were revoked.

        A single bulk UPDATE rather than loading rows and mutating them: the whole point is to
        shut a compromised session down immediately, and one statement is both faster and
        atomic. The ``revoked_at.is_(None)`` guard preserves the original timestamp on tokens
        that were already revoked, keeping the audit trail honest.
        """
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id)
            .where(RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        # session.execute() is typed as returning Result, which has no rowcount. A bulk UPDATE
        # always yields a CursorResult; the cast tells mypy what SQLAlchemy cannot express here.
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        return result.rowcount or 0

    async def revoke_all_for_user(self, user_id: uuid.UUID, revoked_at: datetime) -> int:
        """Kill every live session for a user, across every family.

        ``revoke_family`` ends one rotation chain — the right tool for reuse detection, where
        exactly one compromised chain needs to die. A password reset is a different event: if
        the account was ever going to be reset because a device or a token was compromised,
        every other session is suspect too, not just the one connected to whatever triggered
        this. Nothing short of "every session, everywhere" is the correct response.
        """
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .where(RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        return result.rowcount or 0

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[RefreshToken]:
        """Live tokens for a user — one row per signed-in device."""
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .where(RefreshToken.revoked_at.is_(None))
            .order_by(RefreshToken.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
