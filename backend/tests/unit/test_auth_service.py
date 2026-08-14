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
from app.core.security import hash_password, hash_refresh_token
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.services.auth import AuthService
from app.services.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RefreshTokenReuseDetectedError,
)

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

    def add(self, entity: User) -> User:
        # The real database assigns the id; the fake has to stand in for that.
        if entity.id is None:
            entity.id = uuid.uuid4()
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

    def add(self, entity: RefreshToken) -> RefreshToken:
        if entity.id is None:
            entity.id = uuid.uuid4()
        self.rows[entity.id] = entity
        return entity


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        pass


@pytest.fixture
def users() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def tokens() -> FakeRefreshTokenRepository:
    return FakeRefreshTokenRepository()


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(
    users: FakeUserRepository,
    tokens: FakeRefreshTokenRepository,
    uow: FakeUnitOfWork,
) -> AuthService:
    return AuthService(users=users, refresh_tokens=tokens, uow=uow)


def make_user(
    email: str = "ada@example.com",
    *,
    password: str = PASSWORD,
    is_active: bool = True,
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
    return user


# --------------------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------------------


class TestRegister:
    async def test_creates_user_with_hashed_password(
        self, service: AuthService, users: FakeUserRepository
    ) -> None:
        user = await service.register(email="Ada@Example.COM", password=PASSWORD)

        assert user.email == "ada@example.com"  # normalised at the service boundary
        assert user.password_hash != PASSWORD
        assert users.rows[user.id] is user

    async def test_defaults_to_job_seeker(self, service: AuthService) -> None:
        user = await service.register(email="a@example.com", password=PASSWORD)
        assert user.role is UserRole.JOB_SEEKER

    async def test_can_register_a_recruiter(self, service: AuthService) -> None:
        user = await service.register(
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
