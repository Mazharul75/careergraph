"""The user's skill profile: reading it, and correcting it.

The correction path exists because extraction is not perfect and never will be. A resume that
says "I have no experience with Kubernetes" contains the word Kubernetes; a rule-based matcher
records it. Letting users fix their own profile is cheaper and more honest than pretending the
pipeline is right — and every downstream number (match scores, learning paths) is only as good
as this list.
"""

from __future__ import annotations

import uuid

from app.models.skill import Skill
from app.models.user_skill import SkillSource, SkillStatus, UserSkill
from app.repositories.protocols import (
    SkillRepositoryProtocol,
    UnitOfWork,
    UserSkillRepositoryProtocol,
)
from app.services.exceptions import SkillNotFoundError, SkillNotInProfileError


class SkillProfileService:
    def __init__(
        self,
        *,
        skills: SkillRepositoryProtocol,
        user_skills: UserSkillRepositoryProtocol,
        uow: UnitOfWork,
    ) -> None:
        self._skills = skills
        self._user_skills = user_skills
        self._uow = uow

    async def list_vocabulary(self) -> list[Skill]:
        return await self._skills.list_all()

    async def get_profile(self, *, user_id: uuid.UUID) -> tuple[list[UserSkill], list[UserSkill]]:
        """Return (confirmed, suggested).

        Rejected entries are excluded: they are tombstones that stop a dismissed suggestion
        reappearing after the next upload, not something to show the user again.
        """
        entries = await self._user_skills.list_for_user(
            user_id, statuses=(SkillStatus.CONFIRMED, SkillStatus.SUGGESTED)
        )
        confirmed = [e for e in entries if e.status is SkillStatus.CONFIRMED]
        suggested = [e for e in entries if e.status is SkillStatus.SUGGESTED]
        return confirmed, suggested

    async def add_skill(
        self, *, user_id: uuid.UUID, skill_id: uuid.UUID, proficiency: int | None = None
    ) -> UserSkill:
        """Add a skill manually, or resurrect one previously rejected.

        Adding a skill the user had rejected is a deliberate reversal, so it flips the
        tombstone back to confirmed rather than refusing.
        """
        if await self._skills.get(skill_id) is None:
            raise SkillNotFoundError

        existing = await self._user_skills.get(user_id, skill_id)
        if existing is not None:
            existing.status = SkillStatus.CONFIRMED
            existing.source = SkillSource.MANUAL
            if proficiency is not None:
                existing.proficiency = proficiency
            await self._uow.commit()
            return await self._reload(user_id, skill_id)

        entry = UserSkill(
            user_id=user_id,
            skill_id=skill_id,
            source=SkillSource.MANUAL,
            status=SkillStatus.CONFIRMED,
            proficiency=proficiency,
            occurrences=0,  # never seen in a document — the user asserted it
        )
        self._user_skills.add(entry)
        await self._uow.commit()
        return await self._reload(user_id, skill_id)

    async def update_skill(
        self,
        *,
        user_id: uuid.UUID,
        skill_id: uuid.UUID,
        status: SkillStatus | None = None,
        proficiency: int | None = None,
    ) -> UserSkill:
        """Confirm, reject, or set proficiency on an existing entry."""
        entry = await self._user_skills.get(user_id, skill_id)
        if entry is None:
            raise SkillNotInProfileError

        if status is not None:
            entry.status = status
        if proficiency is not None:
            entry.proficiency = proficiency

        await self._uow.commit()
        return await self._reload(user_id, skill_id)

    async def _reload(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> UserSkill:
        """Re-read an entry with its skill eagerly loaded, ready to serialise.

        A newly constructed UserSkill has no `.skill` populated — `lazy="joined"` applies to
        queries, not to objects built in Python — so returning it directly makes the response
        layer attempt lazy I/O and raise MissingGreenlet.
        """
        entry = await self._user_skills.get_with_skill(user_id, skill_id)
        if entry is None:  # pragma: no cover - only reachable if the row vanished mid-request
            raise SkillNotInProfileError
        return entry

    async def confirm_all_suggestions(self, *, user_id: uuid.UUID) -> int:
        """Accept every outstanding suggestion at once.

        Reviewing forty extracted skills one at a time is the kind of friction that makes
        people abandon the correction step entirely — which leaves the profile wrong and every
        downstream score wrong with it.
        """
        suggested = await self._user_skills.list_for_user(
            user_id, statuses=(SkillStatus.SUGGESTED,)
        )
        for entry in suggested:
            entry.status = SkillStatus.CONFIRMED
        await self._uow.commit()
        return len(suggested)
