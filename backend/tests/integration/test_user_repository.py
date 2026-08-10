"""UserRepository against a real database.

These are integration tests on purpose. Mocking SQLAlchemy would test that the mock behaves
like a mock — it would not catch a broken unique constraint, a CHECK constraint that rejects a
valid row, or an index that doesn't exist.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.repositories.user import UserRepository

pytestmark = pytest.mark.integration


def make_user(email: str = "ada@example.com", **overrides: object) -> User:
    defaults: dict[str, object] = {
        "email": email,
        "password_hash": "not-a-real-hash-phase-1b",
        "full_name": "Ada Lovelace",
    }
    defaults.update(overrides)
    return User(**defaults)  # type: ignore[arg-type]


class TestGetByEmail:
    async def test_finds_existing_user(self, db_session: AsyncSession) -> None:
        repo = UserRepository(db_session)
        repo.add(make_user("ada@example.com"))
        await db_session.flush()

        found = await repo.get_by_email("ada@example.com")

        assert found is not None
        assert found.full_name == "Ada Lovelace"

    async def test_returns_none_for_unknown_address(self, db_session: AsyncSession) -> None:
        repo = UserRepository(db_session)

        assert await repo.get_by_email("nobody@example.com") is None

    @pytest.mark.parametrize("lookup", ["ADA@EXAMPLE.COM", "Ada@Example.Com", " ada@example.com "])
    async def test_lookup_is_case_and_whitespace_insensitive(
        self, db_session: AsyncSession, lookup: str
    ) -> None:
        # A user who types their address with different capitalisation at login must still
        # reach their own account rather than appearing not to exist.
        repo = UserRepository(db_session)
        repo.add(make_user("ada@example.com"))
        await db_session.flush()

        assert await repo.get_by_email(lookup) is not None


class TestConstraints:
    async def test_duplicate_email_is_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        # "One account per address" must be a database guarantee. An application-level check
        # alone loses to two concurrent registrations.
        repo = UserRepository(db_session)
        repo.add(make_user("ada@example.com"))
        await db_session.flush()

        repo.add(make_user("ada@example.com"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_uppercase_email_is_rejected(self, db_session: AsyncSession) -> None:
        # The CHECK constraint is the backstop for code that forgets to normalise.
        db_session.add(make_user("ADA@EXAMPLE.COM"))
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestDefaults:
    async def test_new_user_defaults_to_job_seeker_and_active(
        self, db_session: AsyncSession
    ) -> None:
        user = make_user("new@example.com")
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        assert user.role is UserRole.JOB_SEEKER
        assert user.is_active is True

    async def test_timestamps_are_set_by_the_database(self, db_session: AsyncSession) -> None:
        user = make_user("stamped@example.com")
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        assert user.created_at is not None
        # Timezone-aware, so the value is unambiguous across regions.
        assert user.created_at.tzinfo is not None


class TestExistence:
    async def test_email_exists_reflects_reality(self, db_session: AsyncSession) -> None:
        repo = UserRepository(db_session)
        repo.add(make_user("taken@example.com"))
        await db_session.flush()

        assert await repo.email_exists("TAKEN@example.com") is True
        assert await repo.email_exists("free@example.com") is False


class TestBaseRepository:
    async def test_get_by_id(self, db_session: AsyncSession) -> None:
        repo = UserRepository(db_session)
        user = repo.add(make_user("byid@example.com"))
        await db_session.flush()

        assert (await repo.get(user.id)) is not None
        assert (await repo.get(uuid.uuid4())) is None

    async def test_list_is_paginated(self, db_session: AsyncSession) -> None:
        repo = UserRepository(db_session)
        for i in range(5):
            repo.add(make_user(f"user{i}@example.com"))
        await db_session.flush()

        assert len(await repo.list(limit=2)) == 2
