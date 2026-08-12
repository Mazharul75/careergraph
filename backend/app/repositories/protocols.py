"""Repository interfaces.

This is the part of the repository pattern that actually earns its keep. Services depend on
these ``Protocol`` types, not on the SQLAlchemy-backed classes, so a unit test can pass a
dictionary-backed fake and exercise real business logic with no database at all.

``Protocol`` gives *structural* typing: a class satisfies one of these by having methods with
matching signatures. Neither the real repository nor a test fake needs to inherit from
anything — which means the fakes stay trivially small, and mypy still verifies they match the
contract the service depends on.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from app.models.refresh_token import RefreshToken
from app.models.resume import Resume
from app.models.user import User


class UnitOfWork(Protocol):
    """The transaction boundary, narrowed to what services are allowed to do.

    ``AsyncSession`` satisfies this structurally, so the real implementation is just the
    session. Services get ``commit`` and ``flush`` and nothing else — no ``execute``, so a
    service cannot quietly bypass the repositories and run its own SQL.
    """

    async def commit(self) -> None: ...
    async def flush(self) -> None: ...


class UserRepositoryProtocol(Protocol):
    async def get(self, entity_id: uuid.UUID) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def email_exists(self, email: str) -> bool: ...
    def add(self, entity: User) -> User: ...


class RefreshTokenRepositoryProtocol(Protocol):
    async def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...
    async def revoke_family(self, family_id: uuid.UUID, revoked_at: datetime) -> int: ...
    def add(self, entity: RefreshToken) -> RefreshToken: ...


class ResumeRepositoryProtocol(Protocol):
    async def get_for_user(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume | None: ...
    async def get_with_text(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume | None: ...
    async def list_for_user(self, user_id: uuid.UUID, *, limit: int = 50) -> list[Resume]: ...
    async def count_pending_for_user(self, user_id: uuid.UUID) -> int: ...
    def add(self, entity: Resume) -> Resume: ...


class TaskDispatcher(Protocol):
    """How a service hands work to the queue.

    Abstracted for the same reason the repositories are: a unit test can substitute a recorder
    and assert that a task *would* have been enqueued, with no Redis running and no Celery
    imported. Without this, every test of the upload path would need a live broker.
    """

    def enqueue_resume_parse(self, resume_id: uuid.UUID) -> None: ...
