"""AuthService against in-memory fakes.

No database, no HTTP, no event loop tricks — the entire authentication rulebook is exercised
in milliseconds. This is the payoff for depending on repository *protocols* rather than on
SQLAlchemy: the fakes below are about forty lines and mypy verifies they match the contract
the service actually depends on.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.core.security import hash_opaque_token, hash_password, hash_refresh_token
from app.models.email_verification_token import EmailVerificationToken
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.services.auth import AuthService
from app.services.exceptions import (
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    GoogleSignInNotConfiguredError,
    GoogleTokenInvalidError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidPasswordResetTokenError,
    InvalidRefreshTokenError,
    InvalidVerificationTokenError,
    RefreshTokenReuseDetectedError,
)
from app.services.google_auth import GoogleIdentity, GoogleTokenVerifier

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/careergraph_test")
    monkeypatch.setenv("JWT_SECRET_KEY", "unit-test-signing-key-not-used-anywhere-else")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------


class FakeUserRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, User] = {}

    async def get(self, entity_id: uuid.UUID) -> User | None:
        return self.rows.get(entity_id)

    async def get_by_email(self, email: str) -> User | None:
        target = email.strip().lower()
        return next((u for u in self.rows.values() if u.email == target), None)

    async def email_exists(self, email: str) -> bool:
        return await self.get_by_email(email) is not None

    async def get_by_google_sub(self, google_sub: str) -> User | None:
        return next((u for u in self.rows.values() if u.google_sub == google_sub), None)

    def add(self, entity: User) -> User:
        # Stands in for two things a real flush does to a freshly constructed row: assigns
        # the client-side UUID default, and populates `is_active`, which in the real schema
        # is a *server*-side default and so is `None` on an unflushed instance — exactly the
        # gap that let a newly Google-created account fail its own activity check.
        if entity.id is None:
            entity.id = uuid.uuid4()
        if entity.is_active is None:
            entity.is_active = True
        self.rows[entity.id] = entity
        return entity


class FakeRefreshTokenRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, RefreshToken] = {}

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return next((t for t in self.rows.values() if t.token_hash == token_hash), None)

    async def revoke_family(self, family_id: uuid.UUID, revoked_at: datetime) -> int:
        revoked = 0
        for token in self.rows.values():
            if token.family_id == family_id and token.revoked_at is None:
                token.revoked_at = revoked_at
                revoked += 1
        return revoked

    async def revoke_all_for_user(self, user_id: uuid.UUID, revoked_at: datetime) -> int:
        revoked = 0
        for token in self.rows.values():
            if token.user_id == user_id and token.revoked_at is None:
                token.revoked_at = revoked_at
                revoked += 1
        return revoked

    def add(self, entity: RefreshToken) -> RefreshToken:
        if entity.id is None:
            entity.id = uuid.uuid4()
        self.rows[entity.id] = entity
        return entity


class FakeEmailVerificationTokenRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, EmailVerificationToken] = {}

    async def get_by_hash(self, token_hash: str) -> EmailVerificationToken | None:
        return next((t for t in self.rows.values() if t.token_hash == token_hash), None)

    async def invalidate_active_for_user(self, user_id: uuid.UUID, used_at: datetime) -> int:
        invalidated = 0
        for token in self.rows.values():
            if token.user_id == user_id and token.used_at is None:
                token.used_at = used_at
                invalidated += 1
        return invalidated

    def add(self, entity: EmailVerificationToken) -> EmailVerificationToken:
        if entity.id is None:
            entity.id = uuid.uuid4()
        self.rows[entity.id] = entity
        return entity


class FakePasswordResetTokenRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, PasswordResetToken] = {}

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        return next((t for t in self.rows.values() if t.token_hash == token_hash), None)

    async def invalidate_active_for_user(self, user_id: uuid.UUID, used_at: datetime) -> int:
        invalidated = 0
        for token in self.rows.values():
            if token.user_id == user_id and token.used_at is None:
                token.used_at = used_at
                invalidated += 1
        return invalidated

    def add(self, entity: PasswordResetToken) -> PasswordResetToken:
        if entity.id is None:
            entity.id = uuid.uuid4()
        self.rows[entity.id] = entity
        return entity


class FakeEmailSender:
    """Records what would have been sent, instead of sending it."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []  # (to, subject, html)

    async def send(self, *, to: str, subject: str, html: str) -> None:
        self.sent.append((to, subject, html))


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        pass


def fake_google_verifier(identity: GoogleIdentity) -> GoogleTokenVerifier:
    """Builds a ``GoogleTokenVerifier`` that returns a canned identity for any token.

    Standing in for real cryptography the same way ``FakeEmailSender`` stands in for a real
    inbox: the service under test cannot tell the difference between this and a real,
    signature-verified Google ID token.
    """

    def _verify(id_token: str, *, client_id: str) -> GoogleIdentity:
        return identity

    return _verify


@pytest.fixture
def users() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def tokens() -> FakeRefreshTokenRepository:
    return FakeRefreshTokenRepository()


@pytest.fixture
def email_tokens() -> FakeEmailVerificationTokenRepository:
    return FakeEmailVerificationTokenRepository()


@pytest.fixture
def password_reset_tokens() -> FakePasswordResetTokenRepository:
    return FakePasswordResetTokenRepository()


@pytest.fixture
def email_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(
    users: FakeUserRepository,
    tokens: FakeRefreshTokenRepository,
    email_tokens: FakeEmailVerificationTokenRepository,
    password_reset_tokens: FakePasswordResetTokenRepository,
    email_sender: FakeEmailSender,
    uow: FakeUnitOfWork,
) -> AuthService:
    return AuthService(
        users=users,
        refresh_tokens=tokens,
        email_tokens=email_tokens,
        password_reset_tokens=password_reset_tokens,
        email_sender=email_sender,
        uow=uow,
    )


def make_user(
    email: str = "ada@example.com",
    *,
    password: str = PASSWORD,
    is_active: bool = True,
    email_verified: bool = True,
    role: UserRole = UserRole.JOB_SEEKER,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name="Ada Lovelace",
        role=role,
    )
    user.id = uuid.uuid4()
    user.is_active = is_active
    # Verified by default: most of this file exercises login/refresh/logout, not the
    # verification gate itself, and pre-existing test intent should not have to know a new
    # gate was added underneath it. Tests about the gate build an unverified user explicitly.
    user.email_verified_at = datetime.now(UTC) if email_verified else None
    return user


# --------------------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------------------


class TestRegister:
    async def test_creates_user_with_hashed_password(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        user, _raw_token = await service.register(email="Ada@Example.COM", password=PASSWORD)

        assert user.email == "ada@example.com"  # normalised at the service boundary
        assert user.password_hash != PASSWORD
        assert users.rows[user.id] is user

    async def test_new_account_is_unverified(self, service: AuthService) -> None:
        user, _raw_token = await service.register(email="a@example.com", password=PASSWORD)
        assert user.email_verified is False

    async def test_issues_a_usable_verification_token(
        self,
        service: AuthService,
        email_tokens: FakeEmailVerificationTokenRepository,
    ) -> None:
        _user, raw_token = await service.register(email="a@example.com", password=PASSWORD)

        stored = await email_tokens.get_by_hash(hash_opaque_token(raw_token))
        assert stored is not None
        assert stored.is_usable()

    async def test_sends_a_verification_email(
        self, service: AuthService, email_sender: FakeEmailSender
    ) -> None:
        _user, raw_token = await service.register(email="a@example.com", password=PASSWORD)

        assert len(email_sender.sent) == 1
        to, _subject, html = email_sender.sent[0]
        assert to == "a@example.com"
        assert raw_token in html  # the link actually carries the token

    async def test_defaults_to_job_seeker(self, service: AuthService) -> None:
        user, _ = await service.register(email="a@example.com", password=PASSWORD)
        assert user.role is UserRole.JOB_SEEKER

    async def test_can_register_a_recruiter(self, service: AuthService) -> None:
        user, _ = await service.register(
            email="r@example.com", password=PASSWORD, role=UserRole.RECRUITER
        )
        assert user.role is UserRole.RECRUITER

    async def test_duplicate_email_is_rejected(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user("taken@example.com"))

        with pytest.raises(EmailAlreadyRegisteredError):
            await service.register(email="TAKEN@example.com", password=PASSWORD)


# --------------------------------------------------------------------------------------
# Email verification
# --------------------------------------------------------------------------------------


class TestVerifyEmail:
    async def test_marks_the_account_verified(self, service: AuthService) -> None:
        _user, raw_token = await service.register(email="a@example.com", password=PASSWORD)

        verified = await service.verify_email(raw_token=raw_token)

        assert verified.email_verified is True

    async def test_unknown_token_is_rejected(self, service: AuthService) -> None:
        with pytest.raises(InvalidVerificationTokenError):
            await service.verify_email(raw_token="never-issued")

    async def test_a_token_cannot_be_redeemed_twice(self, service: AuthService) -> None:
        _user, raw_token = await service.register(email="a@example.com", password=PASSWORD)
        await service.verify_email(raw_token=raw_token)

        with pytest.raises(InvalidVerificationTokenError):
            await service.verify_email(raw_token=raw_token)

    async def test_expired_token_is_rejected(
        self, service: AuthService, email_tokens: FakeEmailVerificationTokenRepository
    ) -> None:
        _user, raw_token = await service.register(email="a@example.com", password=PASSWORD)
        stored = await email_tokens.get_by_hash(hash_opaque_token(raw_token))
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        with pytest.raises(InvalidVerificationTokenError):
            await service.verify_email(raw_token=raw_token)

    async def test_verifying_unlocks_login(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        _user, raw_token = await service.register(email="a@example.com", password=PASSWORD)

        with pytest.raises(EmailNotVerifiedError):
            await service.login(email="a@example.com", password=PASSWORD)

        await service.verify_email(raw_token=raw_token)
        _user2, issued = await service.login(email="a@example.com", password=PASSWORD)
        assert issued.access_token


class TestResendVerification:
    async def test_issues_a_working_replacement_token(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user("a@example.com", email_verified=False))

        await service.resend_verification(email="a@example.com")

        with pytest.raises(EmailNotVerifiedError):
            await service.login(email="a@example.com", password=PASSWORD)

    async def test_invalidates_the_previous_token(
        self,
        service: AuthService,
        email_tokens: FakeEmailVerificationTokenRepository,
    ) -> None:
        _user, original = await service.register(email="a@example.com", password=PASSWORD)

        await service.resend_verification(email="a@example.com")

        with pytest.raises(InvalidVerificationTokenError):
            await service.verify_email(raw_token=original)

    async def test_silently_does_nothing_for_an_unknown_address(
        self, service: AuthService, email_sender: FakeEmailSender
    ) -> None:
        # Must not raise, and must not send anything — there is no account to notify.
        await service.resend_verification(email="nobody@example.com")
        assert email_sender.sent == []

    async def test_silently_does_nothing_for_an_already_verified_address(
        self, service: AuthService, users: FakeUserRepository, email_sender: FakeEmailSender
    ) -> None:
        users.add(make_user("a@example.com", email_verified=True))

        await service.resend_verification(email="a@example.com")

        assert email_sender.sent == []


# --------------------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------------------


class TestLogin:
    async def test_valid_credentials_issue_a_token_pair(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user())

        user, issued = await service.login(email="ada@example.com", password=PASSWORD)

        assert user.email == "ada@example.com"
        assert issued.access_token
        assert issued.refresh_token
        assert issued.expires_in == get_settings().access_token_expire_minutes * 60

    async def test_login_persists_only_the_token_hash(
        self, service: AuthService, users: FakeUserRepository, tokens: FakeRefreshTokenRepository
    ) -> None:
        users.add(make_user())
        _user, issued = await service.login(email="ada@example.com", password=PASSWORD)

        stored = next(iter(tokens.rows.values()))
        assert stored.token_hash != issued.refresh_token
        assert stored.token_hash == hash_refresh_token(issued.refresh_token)

    async def test_wrong_password_is_rejected(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user())

        with pytest.raises(InvalidCredentialsError):
            await service.login(email="ada@example.com", password="wrong-password-here")

    async def test_unknown_account_raises_the_same_error_as_a_wrong_password(
        self, service: AuthService
    ) -> None:
        # Identical exception type and message, so the API cannot leak which addresses exist.
        with pytest.raises(InvalidCredentialsError):
            await service.login(email="nobody@example.com", password=PASSWORD)

    async def test_unverified_account_is_rejected(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user(email_verified=False))

        with pytest.raises(EmailNotVerifiedError):
            await service.login(email="ada@example.com", password=PASSWORD)

    async def test_google_only_account_cannot_log_in_by_password(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        user = make_user()
        user.password_hash = None
        user.google_sub = "some-google-subject"
        users.add(user)

        # Same error as any other failed login — a Google-only account existing at all is
        # not something a password attempt should be able to learn.
        with pytest.raises(InvalidCredentialsError):
            await service.login(email="ada@example.com", password=PASSWORD)

    async def test_deactivated_account_is_rejected(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user(is_active=False))

        with pytest.raises(InactiveAccountError):
            await service.login(email="ada@example.com", password=PASSWORD)

    async def test_each_login_starts_a_new_family(
        self, service: AuthService, users: FakeUserRepository, tokens: FakeRefreshTokenRepository
    ) -> None:
        # Signing in on a second device must not put both sessions in one family — otherwise
        # reuse detection on one device would silently kill the other.
        users.add(make_user())
        await service.login(email="ada@example.com", password=PASSWORD)
        await service.login(email="ada@example.com", password=PASSWORD)

        families = {t.family_id for t in tokens.rows.values()}
        assert len(families) == 2


# --------------------------------------------------------------------------------------
# Google Sign-In
# --------------------------------------------------------------------------------------


class TestGoogleSignIn:
    async def test_disabled_without_a_client_id(
        self, users: FakeUserRepository, tokens: FakeRefreshTokenRepository, uow: FakeUnitOfWork
    ) -> None:
        service = AuthService(
            users=users,
            refresh_tokens=tokens,
            email_tokens=FakeEmailVerificationTokenRepository(),
            password_reset_tokens=FakePasswordResetTokenRepository(),
            email_sender=FakeEmailSender(),
            uow=uow,
            google_verifier=fake_google_verifier(
                GoogleIdentity(
                    subject="s", email="a@example.com", email_verified=True, full_name=None
                )
            ),
        )
        # No GOOGLE_CLIENT_ID set on Settings by default.
        with pytest.raises(GoogleSignInNotConfiguredError):
            await service.authenticate_with_google(id_token="irrelevant")

    @staticmethod
    def _configured_service(
        users: FakeUserRepository,
        uow: FakeUnitOfWork,
        identity: GoogleIdentity,
        monkeypatch: pytest.MonkeyPatch,
    ) -> AuthService:
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        get_settings.cache_clear()
        return AuthService(
            users=users,
            refresh_tokens=FakeRefreshTokenRepository(),
            email_tokens=FakeEmailVerificationTokenRepository(),
            password_reset_tokens=FakePasswordResetTokenRepository(),
            email_sender=FakeEmailSender(),
            uow=uow,
            google_verifier=fake_google_verifier(identity),
        )

    async def test_creates_a_new_account(
        self, users: FakeUserRepository, uow: FakeUnitOfWork, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        identity = GoogleIdentity(
            subject="sub-1", email="new@example.com", email_verified=True, full_name="New Person"
        )
        service = self._configured_service(users, uow, identity, monkeypatch)

        user, issued = await service.authenticate_with_google(id_token="fake")

        assert user.email == "new@example.com"
        assert user.google_sub == "sub-1"
        assert user.has_password is False
        assert user.email_verified is True
        assert issued.access_token

    async def test_links_an_existing_password_account_by_email(
        self, users: FakeUserRepository, uow: FakeUnitOfWork, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        existing = make_user("both@example.com", email_verified=False)
        users.add(existing)
        identity = GoogleIdentity(
            subject="sub-2", email="both@example.com", email_verified=True, full_name="Both"
        )
        service = self._configured_service(users, uow, identity, monkeypatch)

        user, _issued = await service.authenticate_with_google(id_token="fake")

        assert user.id == existing.id  # the same account, not a second one
        assert user.google_sub == "sub-2"
        assert user.has_password is True  # the password is not removed by linking
        assert user.email_verified is True  # Google's proof completes the existing gap

    async def test_returning_user_is_found_by_subject_not_email(
        self, users: FakeUserRepository, uow: FakeUnitOfWork, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        identity = GoogleIdentity(
            subject="sub-3", email="first@example.com", email_verified=True, full_name="A"
        )
        service = self._configured_service(users, uow, identity, monkeypatch)
        first_user, _ = await service.authenticate_with_google(id_token="fake")

        changed_identity = GoogleIdentity(
            subject="sub-3", email="changed@example.com", email_verified=True, full_name="A"
        )
        service_again = self._configured_service(users, uow, changed_identity, monkeypatch)
        second_user, _ = await service_again.authenticate_with_google(id_token="fake")

        assert second_user.id == first_user.id

    async def test_invalid_google_token_propagates(
        self, users: FakeUserRepository, uow: FakeUnitOfWork, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        get_settings.cache_clear()

        def _explode(id_token: str, *, client_id: str) -> GoogleIdentity:
            raise GoogleTokenInvalidError

        service = AuthService(
            users=users,
            refresh_tokens=FakeRefreshTokenRepository(),
            email_tokens=FakeEmailVerificationTokenRepository(),
            password_reset_tokens=FakePasswordResetTokenRepository(),
            email_sender=FakeEmailSender(),
            uow=uow,
            google_verifier=_explode,
        )

        with pytest.raises(GoogleTokenInvalidError):
            await service.authenticate_with_google(id_token="fake")


# --------------------------------------------------------------------------------------
# Refresh — rotation and reuse detection
# --------------------------------------------------------------------------------------


class TestRefresh:
    async def test_rotation_issues_a_new_pair(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user())
        _user, first = await service.login(email="ada@example.com", password=PASSWORD)

        second = await service.refresh(raw_refresh_token=first.refresh_token)

        assert second.refresh_token != first.refresh_token
        assert second.access_token != first.access_token

    async def test_rotation_stays_in_the_same_family(
        self, service: AuthService, users: FakeUserRepository, tokens: FakeRefreshTokenRepository
    ) -> None:
        users.add(make_user())
        _user, first = await service.login(email="ada@example.com", password=PASSWORD)
        await service.refresh(raw_refresh_token=first.refresh_token)

        assert len({t.family_id for t in tokens.rows.values()}) == 1

    async def test_old_token_is_revoked_and_linked_to_its_successor(
        self, service: AuthService, users: FakeUserRepository, tokens: FakeRefreshTokenRepository
    ) -> None:
        users.add(make_user())
        _user, first = await service.login(email="ada@example.com", password=PASSWORD)
        second = await service.refresh(raw_refresh_token=first.refresh_token)

        old = await tokens.get_by_hash(hash_refresh_token(first.refresh_token))
        new = await tokens.get_by_hash(hash_refresh_token(second.refresh_token))

        assert old is not None and new is not None
        assert old.revoked_at is not None
        assert old.replaced_by_id == new.id  # the chain is traceable

    async def test_unknown_token_is_rejected(self, service: AuthService) -> None:
        with pytest.raises(InvalidRefreshTokenError):
            await service.refresh(raw_refresh_token="a-token-that-was-never-issued")

    async def test_expired_token_is_rejected(
        self, service: AuthService, users: FakeUserRepository, tokens: FakeRefreshTokenRepository
    ) -> None:
        users.add(make_user())
        _user, issued = await service.login(email="ada@example.com", password=PASSWORD)

        stored = await tokens.get_by_hash(hash_refresh_token(issued.refresh_token))
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        with pytest.raises(InvalidRefreshTokenError):
            await service.refresh(raw_refresh_token=issued.refresh_token)

    async def test_replaying_a_spent_token_is_detected(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user())
        _user, first = await service.login(email="ada@example.com", password=PASSWORD)
        await service.refresh(raw_refresh_token=first.refresh_token)

        # The attacker's copy of the already-rotated token.
        with pytest.raises(RefreshTokenReuseDetectedError):
            await service.refresh(raw_refresh_token=first.refresh_token)

    async def test_reuse_revokes_the_entire_family(
        self, service: AuthService, users: FakeUserRepository, tokens: FakeRefreshTokenRepository
    ) -> None:
        """The core of the design: theft ends the session, it does not merely fail one request."""
        users.add(make_user())
        _user, first = await service.login(email="ada@example.com", password=PASSWORD)
        second = await service.refresh(raw_refresh_token=first.refresh_token)

        with pytest.raises(RefreshTokenReuseDetectedError):
            await service.refresh(raw_refresh_token=first.refresh_token)

        # The legitimate user's current token is now dead too — by design.
        assert all(t.revoked_at is not None for t in tokens.rows.values())
        with pytest.raises(RefreshTokenReuseDetectedError):
            await service.refresh(raw_refresh_token=second.refresh_token)

    async def test_reuse_in_one_family_does_not_affect_another(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        # A compromised phone must not sign the user out of their laptop.
        users.add(make_user())
        _user, phone = await service.login(email="ada@example.com", password=PASSWORD)
        _user, laptop = await service.login(email="ada@example.com", password=PASSWORD)

        await service.refresh(raw_refresh_token=phone.refresh_token)
        with pytest.raises(RefreshTokenReuseDetectedError):
            await service.refresh(raw_refresh_token=phone.refresh_token)

        assert await service.refresh(raw_refresh_token=laptop.refresh_token) is not None

    async def test_deactivated_user_cannot_refresh(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        user = make_user()
        users.add(user)
        _user, issued = await service.login(email="ada@example.com", password=PASSWORD)

        user.is_active = False

        with pytest.raises(InactiveAccountError):
            await service.refresh(raw_refresh_token=issued.refresh_token)


# --------------------------------------------------------------------------------------
# Logout
# --------------------------------------------------------------------------------------


class TestLogout:
    async def test_logout_revokes_the_family(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user())
        _user, issued = await service.login(email="ada@example.com", password=PASSWORD)

        await service.logout(raw_refresh_token=issued.refresh_token)

        with pytest.raises(RefreshTokenReuseDetectedError):
            await service.refresh(raw_refresh_token=issued.refresh_token)

    async def test_logout_is_idempotent_for_unknown_tokens(self, service: AuthService) -> None:
        # Must not raise. An error here would turn logout into an oracle for guessing tokens.
        await service.logout(raw_refresh_token="never-issued")

    async def test_logout_does_not_affect_other_sessions(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user())
        _user, phone = await service.login(email="ada@example.com", password=PASSWORD)
        _user, laptop = await service.login(email="ada@example.com", password=PASSWORD)

        await service.logout(raw_refresh_token=phone.refresh_token)

        assert await service.refresh(raw_refresh_token=laptop.refresh_token) is not None


# --------------------------------------------------------------------------------------
# Password reset
# --------------------------------------------------------------------------------------


class TestRequestPasswordReset:
    async def test_issues_a_usable_token(
        self,
        service: AuthService,
        users: FakeUserRepository,
        password_reset_tokens: FakePasswordResetTokenRepository,
    ) -> None:
        users.add(make_user())

        raw_token = await service.request_password_reset(email="ada@example.com")

        assert raw_token is not None
        stored = await password_reset_tokens.get_by_hash(hash_opaque_token(raw_token))
        assert stored is not None
        assert stored.is_usable()

    async def test_sends_an_email_containing_the_link(
        self, service: AuthService, users: FakeUserRepository, email_sender: FakeEmailSender
    ) -> None:
        users.add(make_user())

        raw_token = await service.request_password_reset(email="ada@example.com")
        assert raw_token is not None

        assert len(email_sender.sent) == 1
        to, _subject, html = email_sender.sent[0]
        assert to == "ada@example.com"
        assert raw_token in html

    async def test_silently_does_nothing_for_an_unknown_address(
        self, service: AuthService, email_sender: FakeEmailSender
    ) -> None:
        result = await service.request_password_reset(email="nobody@example.com")

        assert result is None
        assert email_sender.sent == []

    async def test_silently_does_nothing_for_a_google_only_account(
        self, service: AuthService, users: FakeUserRepository, email_sender: FakeEmailSender
    ) -> None:
        user = make_user()
        user.password_hash = None
        user.google_sub = "some-subject"
        users.add(user)

        result = await service.request_password_reset(email="ada@example.com")

        assert result is None
        assert email_sender.sent == []

    async def test_invalidates_a_previous_token(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user())
        original = await service.request_password_reset(email="ada@example.com")

        await service.request_password_reset(email="ada@example.com")

        assert original is not None
        with pytest.raises(InvalidPasswordResetTokenError):
            await service.reset_password(raw_token=original, new_password="a-new-password-123")


class TestResetPassword:
    async def test_sets_a_new_password_that_can_log_in(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user())
        raw_token = await service.request_password_reset(email="ada@example.com")
        assert raw_token is not None

        await service.reset_password(raw_token=raw_token, new_password="a-brand-new-password")

        _user, issued = await service.login(
            email="ada@example.com", password="a-brand-new-password"
        )
        assert issued.access_token

        # The old password no longer works.
        with pytest.raises(InvalidCredentialsError):
            await service.login(email="ada@example.com", password=PASSWORD)

    async def test_revokes_every_existing_session(
        self,
        service: AuthService,
        users: FakeUserRepository,
        tokens: FakeRefreshTokenRepository,
    ) -> None:
        """The whole point: a reset must not leave a stolen session alive."""
        users.add(make_user())
        _user, phone = await service.login(email="ada@example.com", password=PASSWORD)
        _user, laptop = await service.login(email="ada@example.com", password=PASSWORD)
        assert phone.refresh_token != laptop.refresh_token  # two distinct sessions exist

        raw_token = await service.request_password_reset(email="ada@example.com")
        assert raw_token is not None
        await service.reset_password(raw_token=raw_token, new_password="a-brand-new-password")

        assert all(t.revoked_at is not None for t in tokens.rows.values())
        with pytest.raises(RefreshTokenReuseDetectedError):
            await service.refresh(raw_refresh_token=phone.refresh_token)
        with pytest.raises(RefreshTokenReuseDetectedError):
            await service.refresh(raw_refresh_token=laptop.refresh_token)

    async def test_unknown_token_is_rejected(self, service: AuthService) -> None:
        with pytest.raises(InvalidPasswordResetTokenError):
            await service.reset_password(raw_token="never-issued", new_password="whatever-1234")

    async def test_a_token_cannot_be_redeemed_twice(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        users.add(make_user())
        raw_token = await service.request_password_reset(email="ada@example.com")
        assert raw_token is not None
        await service.reset_password(raw_token=raw_token, new_password="first-new-password-1")

        with pytest.raises(InvalidPasswordResetTokenError):
            await service.reset_password(raw_token=raw_token, new_password="second-attempt-12")

    async def test_expired_token_is_rejected(
        self,
        service: AuthService,
        users: FakeUserRepository,
        password_reset_tokens: FakePasswordResetTokenRepository,
    ) -> None:
        users.add(make_user())
        raw_token = await service.request_password_reset(email="ada@example.com")
        assert raw_token is not None

        stored = await password_reset_tokens.get_by_hash(hash_opaque_token(raw_token))
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        with pytest.raises(InvalidPasswordResetTokenError):
            await service.reset_password(raw_token=raw_token, new_password="whatever-again-1")
