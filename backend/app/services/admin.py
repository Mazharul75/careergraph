"""Operator actions.

Thin over the repository, but not skippable: the two guards below are business rules, not
data access, and putting them here keeps them out of the route handler where they would be
easy to forget on the next endpoint.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.user import User, UserRole
from app.repositories.admin import AdminRepository, AdminUserRow, SystemStats
from app.repositories.protocols import UnitOfWork, UserRepositoryProtocol
from app.services.exceptions import (
    CannotDemoteLastAdminError,
    CannotSuspendYourselfError,
    UserNotFoundError,
)


class AdminService:
    def __init__(
        self,
        *,
        admin_repo: AdminRepository,
        users: UserRepositoryProtocol,
        uow: UnitOfWork,
    ) -> None:
        self._admin = admin_repo
        self._users = users
        self._uow = uow

    async def stats(self) -> SystemStats:
        return await self._admin.stats()

    async def list_users(self, *, limit: int = 50, offset: int = 0) -> list[AdminUserRow]:
        return await self._admin.list_users(limit=limit, offset=offset)

    async def set_active(self, *, actor: User, user_id: uuid.UUID, is_active: bool) -> User:
        """Suspend or restore an account.

        Deactivation rather than deletion, matching the model's design: the account stops
        authenticating immediately (``get_current_user`` re-reads ``is_active`` on every
        request, which is why a JWT cannot outlive a suspension), while their resumes and
        goals survive in case the suspension was a mistake.
        """
        if actor.id == user_id and not is_active:
            # Locking yourself out is never the intent, and recovering needs database access.
            raise CannotSuspendYourselfError

        target = await self._users.get(user_id)
        if target is None:
            raise UserNotFoundError

        target.is_active = is_active
        await self._uow.commit()
        return target

    async def set_role(self, *, actor: User, user_id: uuid.UUID, role: UserRole) -> User:
        """Change a user's role.

        Refuses to remove the last admin. Without this an operator can demote themselves and
        leave the system with no one able to administer it — recoverable only by running SQL
        by hand against production, which is exactly the situation an admin panel exists to
        avoid.
        """
        target = await self._users.get(user_id)
        if target is None:
            raise UserNotFoundError

        if target.role is UserRole.ADMIN and role is not UserRole.ADMIN:
            stats = await self._admin.stats()
            if stats.admins <= 1:
                raise CannotDemoteLastAdminError

        target.role = role
        await self._uow.commit()
        return target

    async def verify_email(self, *, user_id: uuid.UUID) -> User:
        """Mark an account verified without a real email ever being delivered.

        Exists for exactly one situation: a transactional email provider's free/sandbox tier
        (Resend's included) can only deliver to the address that owns the account until a
        real domain is verified, so anyone else who registers is otherwise stuck forever with
        no way to prove they control their inbox. An operator manually vouching for the
        account is the deliberate escape hatch — no different in kind from a support agent
        confirming an identity by other means.

        Idempotent: verifying an already-verified account is a no-op, not an error, so a
        double-click in the console cannot raise anything worth showing the operator.
        """
        target = await self._users.get(user_id)
        if target is None:
            raise UserNotFoundError

        if target.email_verified_at is None:
            target.email_verified_at = datetime.now(UTC)
            await self._uow.commit()
        return target
