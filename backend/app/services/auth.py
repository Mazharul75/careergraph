"""Authentication business logic.

Note what this module does not import: FastAPI, ``Request``, ``HTTPException``, status codes,
or SQLAlchemy. It depends only on repository *protocols* and the security primitives. That is
what makes the whole file unit-testable against in-memory fakes, and what will let a Celery
task reuse it unchanged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    refresh_token_expiry,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.repositories.protocols import (
    RefreshTokenRepositoryProtocol,
    UnitOfWork,
    UserRepositoryProtocol,
)
from app.services.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RefreshTokenReuseDetectedError,
)


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    """A freshly minted token pair. The raw refresh token exists only here and in the response."""

    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    def __init__(
        self,
        *,
        users: UserRepositoryProtocol,
        refresh_tokens: RefreshTokenRepositoryProtocol,
        uow: UnitOfWork,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._uow = uow

    # ----------------------------------------------------------------------------------
    # Registration
    # ----------------------------------------------------------------------------------

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str | None = None,
        role: UserRole = UserRole.JOB_SEEKER,
    ) -> User:
        normalised = email.strip().lower()

        if await self._users.email_exists(normalised):
            # This does leak whether an address is registered, and that is a real trade-off.
            # The alternative — accepting the registration and sending a "you already have an
            # account" email — requires email delivery we do not have. Rate limiting in
            # Phase 5 is what stops this being usable for bulk enumeration.
            raise EmailAlreadyRegisteredError

        user = User(
            email=normalised,
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
        )
        self._users.add(user)
        await self._uow.commit()
        return user

    # ----------------------------------------------------------------------------------
    # Login
    # ----------------------------------------------------------------------------------

    async def login(self, *, email: str, password: str) -> tuple[User, IssuedTokens]:
        user = await self._users.get_by_email(email.strip().lower())

        if user is None:
            # Verify against a throwaway hash so a missing account costs the same ~50ms as a
            # wrong password. Returning early here would make account existence measurable
            # with a stopwatch.
            verify_password(DUMMY_PASSWORD_HASH, password)
            raise InvalidCredentialsError

        if not verify_password(user.password_hash, password):
            raise InvalidCredentialsError

        # Checked *after* the password, so an attacker cannot distinguish "deactivated" from
        # "wrong password" without already knowing the password.
        if not user.is_active:
            raise InactiveAccountError

        # Transparent upgrade: if the cost parameters have been raised since this hash was
        # written, rewrite it now, while the plaintext is legitimately in hand.
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        tokens = await self._issue_tokens(user=user, family_id=uuid.uuid4())
        await self._uow.commit()
        return user, tokens

    # ----------------------------------------------------------------------------------
    # Refresh — rotation with reuse detection
    # ----------------------------------------------------------------------------------

    async def refresh(self, *, raw_refresh_token: str) -> IssuedTokens:
        """Exchange a refresh token for a new pair, invalidating the old one.

        The security-critical path in the whole application. Order matters:

        1. Unknown token → reject. Nothing to revoke; it was never issued.
        2. **Already revoked → reuse detected.** A single-use token presented twice means a
           copy exists somewhere it should not. Revoke the entire family, ending the attacker's
           session *and* the legitimate user's, forcing re-authentication.
        3. Expired → reject, but do not treat as an attack; expiry is normal.
        4. Otherwise rotate: revoke this token, issue a successor in the same family, and link
           them so the chain can be traced afterwards.
        """
        now = datetime.now(UTC)
        token_hash = hash_refresh_token(raw_refresh_token)
        stored = await self._refresh_tokens.get_by_hash(token_hash)

        if stored is None:
            raise InvalidRefreshTokenError

        if stored.is_revoked:
            await self._refresh_tokens.revoke_family(stored.family_id, now)
            await self._uow.commit()
            raise RefreshTokenReuseDetectedError

        if stored.is_expired(now=now):
            raise InvalidRefreshTokenError

        user = await self._users.get(stored.user_id)
        if user is None:
            raise InvalidRefreshTokenError
        if not user.is_active:
            raise InactiveAccountError

        stored.revoked_at = now
        tokens = await self._issue_tokens(user=user, family_id=stored.family_id, previous=stored)
        await self._uow.commit()
        return tokens

    # ----------------------------------------------------------------------------------
    # Logout
    # ----------------------------------------------------------------------------------

    async def logout(self, *, raw_refresh_token: str) -> None:
        """End a session by revoking its whole family.

        Revoking the family rather than the single token means a user who suspects their device
        was compromised gets a real logout, not one that a stale token can undo.

        Never raises for an unknown token: logout is idempotent, and reporting "that token
        doesn't exist" would turn this endpoint into a token oracle.
        """
        stored = await self._refresh_tokens.get_by_hash(hash_refresh_token(raw_refresh_token))
        if stored is not None:
            await self._refresh_tokens.revoke_family(stored.family_id, datetime.now(UTC))
        await self._uow.commit()

    # ----------------------------------------------------------------------------------
    # Internals
    # ----------------------------------------------------------------------------------

    async def _issue_tokens(
        self,
        *,
        user: User,
        family_id: uuid.UUID,
        previous: RefreshToken | None = None,
    ) -> IssuedTokens:
        settings = get_settings()
        raw_token, token_hash = generate_refresh_token()

        record = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=refresh_token_expiry(),
        )
        self._refresh_tokens.add(record)

        if previous is not None:
            # Flush so the successor has a database-assigned id to link back to.
            await self._uow.flush()
            previous.replaced_by_id = record.id

        return IssuedTokens(
            access_token=create_access_token(user_id=user.id, role=user.role.value),
            refresh_token=raw_token,
            expires_in=settings.access_token_expire_minutes * 60,
        )
