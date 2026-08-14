"""Skill vocabulary and user skill-profile data access."""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, Select, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import joinedload, selectinload

from app.models.skill import Skill
from app.models.user_skill import SkillSource, SkillStatus, UserSkill
from app.repositories.base import BaseRepository
from app.services.skill_matching import VocabularyEntry


def _vocabulary_query() -> Select[tuple[Skill]]:
    # selectinload rather than lazy access: without it, reading `.aliases` on 113 skills issues
    # 113 extra queries — the N+1 problem — and in async SQLAlchemy it raises MissingGreenlet
    # instead, because the implicit I/O happens outside an await.
    return select(Skill).options(selectinload(Skill.aliases))


def to_vocabulary(skills: list[Skill]) -> list[VocabularyEntry]:
    """Convert ORM rows into the matcher's plain dataclasses.

    The boundary that keeps `skill_matching` free of SQLAlchemy: the matcher never sees a
    model, so it can be unit-tested with three handwritten entries and no database.
    """
    return [
        VocabularyEntry(
            skill_id=skill.id,
            canonical_name=skill.canonical_name,
            terms=(skill.canonical_name, *(alias.term for alias in skill.aliases)),
            requires_exact_case=skill.requires_exact_case,
        )
        for skill in skills
    ]


class SkillRepository(BaseRepository[Skill]):
    model = Skill

    async def list_all(self) -> list[Skill]:
        result = await self._session.execute(_vocabulary_query().order_by(Skill.canonical_name))
        return list(result.scalars().all())

    async def get_by_slug(self, slug: str) -> Skill | None:
        result = await self._session.execute(
            _vocabulary_query().where(Skill.slug == slug.strip().lower())
        )
        return result.scalar_one_or_none()

    async def load_vocabulary(self) -> list[VocabularyEntry]:
        return to_vocabulary(await self.list_all())


class UserSkillRepository(BaseRepository[UserSkill]):
    model = UserSkill

    async def list_for_user(
        self, user_id: uuid.UUID, *, statuses: tuple[SkillStatus, ...] | None = None
    ) -> list[UserSkill]:
        stmt = select(UserSkill).where(UserSkill.user_id == user_id)
        if statuses:
            stmt = stmt.where(UserSkill.status.in_(statuses))
        # Confirmed first, then most-mentioned — a sensible default ordering for the UI that
        # does not require the client to sort.
        stmt = stmt.order_by(UserSkill.status, UserSkill.occurrences.desc())
        result = await self._session.execute(stmt)
        return list(result.unique().scalars().all())

    async def get(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> UserSkill | None:  # type: ignore[override]
        return await self._session.get(UserSkill, (user_id, skill_id))

    async def get_with_skill(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> UserSkill | None:
        """Fetch an entry with its `skill` relationship guaranteed loaded.

        `lazy="joined"` on the relationship only applies to *queries*. An entry constructed in
        Python and committed has no `.skill` populated, so serialising it triggers a lazy load
        — which in async SQLAlchemy raises MissingGreenlet rather than merely being slow.

        `populate_existing()` is the load-bearing part: without it, the identity map returns
        the same unloaded instance this session already holds and the eager option is ignored.
        """
        stmt = (
            select(UserSkill)
            .where(UserSkill.user_id == user_id, UserSkill.skill_id == skill_id)
            .options(joinedload(UserSkill.skill))
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def rejected_skill_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        """Skills this user has explicitly dismissed.

        Read before every re-extraction so a rejected suggestion is never resurrected by the
        next resume upload.
        """
        stmt = select(UserSkill.skill_id).where(
            UserSkill.user_id == user_id, UserSkill.status == SkillStatus.REJECTED
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    async def upsert_extracted(
        self, user_id: uuid.UUID, matches: list[tuple[uuid.UUID, int]]
    ) -> int:
        """Record extracted skills, leaving the user's own decisions intact.

        A plain INSERT would violate the composite primary key on re-upload, and a
        DELETE-then-INSERT would wipe confirmations and proficiencies the user set by hand. So:
        ``ON CONFLICT DO UPDATE``, refreshing only the occurrence count, and only for rows the
        user has not already ruled on.
        """
        if not matches:
            return 0

        stmt = pg_insert(UserSkill).values(
            [
                {
                    "user_id": user_id,
                    "skill_id": skill_id,
                    "source": SkillSource.EXTRACTED,
                    "status": SkillStatus.SUGGESTED,
                    "occurrences": min(occurrences, 32767),  # SmallInteger ceiling
                }
                for skill_id, occurrences in matches
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[UserSkill.user_id, UserSkill.skill_id],
            set_={"occurrences": stmt.excluded.occurrences},
            # Never overwrite a decision the user has made.
            where=UserSkill.status == SkillStatus.SUGGESTED,
        )
        # A bulk INSERT ... ON CONFLICT always yields a CursorResult; session.execute is
        # typed as returning the narrower Result, which has no rowcount.
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        return result.rowcount or 0
