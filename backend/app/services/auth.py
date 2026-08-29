"""Authentication business logic.

Note what this module does not import: FastAPI, ``Request``, ``HTTPException``, status codes,
or SQLAlchemy. It depends only on repository *protocols* and the security primitives. That is
what makes the whole file unit-testable against in-memory fakes, and what will let a Celery
task reuse it unchanged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_opaque_token,
    generate_refresh_token,
    hash_opaque_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    refresh_token_expiry,
    verify_password,
)
from app.models.email_verification_token import EmailVerificationToken
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.repositories.protocols import (
    EmailVerificationTokenRepositoryProtocol,
    PasswordResetTokenRepositoryProtocol,
    RefreshTokenRepositoryProtocol,
    UnitOfWork,
    UserRepositoryProtocol,
)
from app.services.email import (
    EmailSenderProtocol,
    password_reset_email_html,
    verification_email_html,
)
from app.services.exceptions import (
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    GoogleSignInNotConfiguredError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidPasswordResetTokenError,
    InvalidRefreshTokenError,
    InvalidVerificationTokenError,
    RefreshTokenReuseDetectedError,
)
from app.services.google_auth import GoogleTokenVerifier, verify_google_id_token


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
        email_tokens: EmailVerificationTokenRepositoryProtocol,
        password_reset_tokens: PasswordResetTokenRepositoryProtocol,
        email_sender: EmailSenderProtocol,
        uow: UnitOfWork,
        google_verifier: GoogleTokenVerifier = verify_google_id_token,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._email_tokens = email_tokens
        self._password_reset_tokens = password_reset_tokens
        self._email_sender = email_sender
        self._uow = uow
        # Defaulted to the real PyJWT-backed verifier, and injectable so a unit test can
        # supply a fake identity without constructing a real signed Google JWT or reaching
        # Google's network — the same reasoning as TaskDispatcher.
        self._google_verifier = google_verifier

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
    ) -> tuple[User, str]:
        """Create an unverified account and issue a verification token.

        Returns ``(user, raw_verification_token)``. The token is always generated and stored
        — email delivery is a best-effort side effect layered on top, not a precondition —
        and it is the caller (the API route) that decides whether the raw value is ever
        allowed to leave the process. See ``Settings.exposes_dev_verification_tokens``.
        """
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
        # `user.id` has a client-side default (`uuid.uuid4`), but SQLAlchemy only evaluates a
        # client-side default during flush, not at construction — the flush below is what
        # actually assigns it, and the token row built next needs that real id for its FK.
        # It also means `user.is_active` — server-default only — comes back populated instead
        # of the `None` an unflushed instance would otherwise show.
        await self._uow.flush()

        raw_token = await self._issue_verification_token(user)
        await self._uow.commit()

        await self._send_verification_email(user, raw_token)
        return user, raw_token

    # ----------------------------------------------------------------------------------
    # Email verification
    # ----------------------------------------------------------------------------------

    async def verify_email(self, *, raw_token: str) -> User:
        """Redeem an emailed link.

        One generic error for "no such token", "already used", and "expired" — the token is
        256 random bits, so there is no meaningful enumeration risk to guard against by
        distinguishing them, and a single message is simpler for the frontend to render.
        """
        stored = await self._email_tokens.get_by_hash(hash_opaque_token(raw_token))
        if stored is None or not stored.is_usable():
            raise InvalidVerificationTokenError

        now = datetime.now(UTC)
        stored.used_at = now

        user = await self._users.get(stored.user_id)
        if user is None:  # pragma: no cover - the FK guarantees this cannot happen
            raise InvalidVerificationTokenError

        if user.email_verified_at is None:
            user.email_verified_at = now

        await self._uow.commit()
        return user

    async def resend_verification(self, *, email: str) -> None:
        """Issue a fresh link, silently, for accounts that are missing exactly one.

        Always returns normally — never raises, never reports whether the address exists or
        was already verified. That silence is deliberate: a "resend" endpoint that answers
        differently for a known-unverified address than for an unknown one is a second
        enumeration oracle on top of the one registration already accepts, and there is no
        reason to add a second.
        """
        user = await self._users.get_by_email(email.strip().lower())
        if user is None or user.email_verified_at is not None:
            return

        now = datetime.now(UTC)
        await self._email_tokens.invalidate_active_for_user(user.id, now)
        raw_token = await self._issue_verification_token(user)
        await self._uow.commit()

        await self._send_verification_email(user, raw_token)

    async def _issue_verification_token(self, user: User) -> str:
        settings = get_settings()
        raw_token, token_hash = generate_opaque_token()
        self._email_tokens.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC)
                + timedelta(hours=settings.email_verification_token_expire_hours),
            )
        )
        return raw_token

    async def _send_verification_email(self, user: User, raw_token: str) -> None:
        settings = get_settings()
        verify_url = f"{settings.frontend_url}/verify-email?token={raw_token}"
        await self._email_sender.send(
            to=user.email,
            subject="Confirm your email for CareerGraph",
            html=verification_email_html(full_name=user.full_name, verify_url=verify_url),
        )

    # ----------------------------------------------------------------------------------
    # Password reset
    # ----------------------------------------------------------------------------------

    async def request_password_reset(self, *, email: str) -> str | None:
        """Issue a reset link, silently, for an account that can actually use one.

        Returns the raw token (for the local/CI dev-mode response field) or ``None`` when
        there is nothing to do. Three cases collapse into that same silent ``None``, on
        purpose — an endpoint that answers differently for "no such account", "Google-only,
        no password to reset", and "here is your link" would leak all three distinctions to
        anyone willing to try addresses:

        * no account with this address
        * an account that exists but has no password to reset (Google-only)
        """
        user = await self._users.get_by_email(email.strip().lower())
        if user is None or not user.has_password:
            return None

        now = datetime.now(UTC)
        await self._password_reset_tokens.invalidate_active_for_user(user.id, now)

        settings = get_settings()
        raw_token, token_hash = generate_opaque_token()
        self._password_reset_tokens.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=now + timedelta(hours=settings.password_reset_token_expire_hours),
            )
        )
        await self._uow.commit()

        reset_url = f"{settings.frontend_url}/reset-password?token={raw_token}"
        await self._email_sender.send(
            to=user.email,
            subject="Reset your CareerGraph password",
            html=password_reset_email_html(full_name=user.full_name, reset_url=reset_url),
        )
        return raw_token

    async def reset_password(self, *, raw_token: str, new_password: str) -> User:
        """Redeem a reset link and set a new password.

        The security-critical side effect is the last line: every existing session is
        revoked, across every device and every refresh-token family. If this reset was
        triggered because a device or a token was compromised, leaving old sessions alive
        would defeat the entire point of resetting the password in the first place — the
        attacker's already-issued access token would keep working until it happened to
        expire on its own.
        """
        stored = await self._password_reset_tokens.get_by_hash(hash_opaque_token(raw_token))
        if stored is None or not stored.is_usable():
            raise InvalidPasswordResetTokenError

        user = await self._users.get(stored.user_id)
        if user is None:  # pragma: no cover - the FK guarantees this cannot happen
            raise InvalidPasswordResetTokenError

        now = datetime.now(UTC)
        stored.used_at = now
        user.password_hash = hash_password(new_password)
        await self._refresh_tokens.revoke_all_for_user(user.id, now)

        await self._uow.commit()
        return user

    # ----------------------------------------------------------------------------------
    # Login
    # ----------------------------------------------------------------------------------

    async def login(self, *, email: str, password: str) -> tuple[User, IssuedTokens]:
        user = await self._users.get_by_email(email.strip().lower())
        # Narrowed into a local rather than re-reading `user.password_hash`: mypy cannot
        # follow `user.has_password` back to a guarantee about the attribute's type, but it
        # can follow an explicit `is None` check on a plain local variable.
        existing_hash = user.password_hash if user is not None else None

        if user is None or existing_hash is None:
            # Verify against a throwaway hash so a missing account — or a real one that can
            # only sign in via Google — costs the same ~50ms as a wrong password. Returning
            # early here would make both cases measurable with a stopwatch, and a
            # Google-only account existing at all is not this caller's business to learn.
            verify_password(DUMMY_PASSWORD_HASH, password)
            raise InvalidCredentialsError

        if not verify_password(existing_hash, password):
            raise InvalidCredentialsError

        # Checked *after* the password, so an attacker cannot distinguish "deactivated" from
        # "wrong password" without already knowing the password.
        if not user.is_active:
            raise InactiveAccountError

        # Also after the password: an unverified account is a real account with a real
        # password, and confirming that much to someone who typed the correct password is not
        # a new leak — they already knew it existed.
        if not user.email_verified:
            raise EmailNotVerifiedError

        # Transparent upgrade: if the cost parameters have been raised since this hash was
        # written, rewrite it now, while the plaintext is legitimately in hand.
        if password_needs_rehash(existing_hash):
            user.password_hash = hash_password(password)

        tokens = await self._issue_tokens(user=user, family_id=uuid.uuid4())
        await self._uow.commit()
        return user, tokens

    # ----------------------------------------------------------------------------------
    # Google Sign-In
    # ----------------------------------------------------------------------------------

    async def authenticate_with_google(self, *, id_token: str) -> tuple[User, IssuedTokens]:
        """Exchange a Google ID token for our own access/refresh pair.

        Never gated on ``email_verified_at``: a valid Google ID token is itself proof of
        control of the mailbox, at least as strong as clicking our own emailed link, so there
        is nothing further to wait for. The verification flag is still set as a side effect
        when Google's own token says the address is verified, purely so the account is in the
        same state a password account reaches after confirming its email.
        """
        settings = get_settings()
        if settings.google_client_id is None:
            raise GoogleSignInNotConfiguredError

        identity = self._google_verifier(id_token, client_id=settings.google_client_id)
        now = datetime.now(UTC)

        user = await self._users.get_by_google_sub(identity.subject)

        if user is None:
            # Fall back to email — this is account *linking*, not a second account. A person
            # who registered with a password and later clicks "Continue with Google" using
            # the same address should land in the one account they already have.
            user = await self._users.get_by_email(identity.email)
            if user is not None:
                user.google_sub = identity.subject
            else:
                user = User(
                    email=identity.email,
                    password_hash=None,
                    full_name=identity.full_name,
                    role=UserRole.JOB_SEEKER,
                    google_sub=identity.subject,
                )
                self._users.add(user)
                # Same reasoning as `register()`: a freshly constructed, unflushed User has
                # neither its client-side `id` default nor its server-side `is_active`
                # default populated yet, and both are read below.
                await self._uow.flush()

        if identity.email_verified and user.email_verified_at is None:
            user.email_verified_at = now

        if not user.is_active:
            raise InactiveAccountError

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
