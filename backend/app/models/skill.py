"""Canonical skill vocabulary.

This table is the spine of the product. Every skill mentioned anywhere — in a resume, in a job
description, in a learning path — resolves to exactly one row here. Storing skill *names* on
user or job rows instead would make "Postgres" and "PostgreSQL" different skills, and would
make renaming one an update across every row that mentions it.

In Phase 3 this becomes the node set of the skill-dependency graph; `skill_edges` will hold the
prerequisite relationships between these rows.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SkillCategory(enum.StrEnum):
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    DATABASE = "database"
    INFRASTRUCTURE = "infrastructure"
    DATA_ML = "data_ml"
    TOOL = "tool"
    CONCEPT = "concept"


class Skill(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "skills"

    canonical_name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )

    # A stable, lowercase, punctuation-free handle. Used in URLs and as the join key for seed
    # data, so the display name can be corrected ("Nodejs" → "Node.js") without breaking links
    # or orphaning rows.
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    category: Mapped[SkillCategory] = mapped_column(
        Enum(
            SkillCategory,
            name="skill_category",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )

    # Rough learning effort, 1 (a weekend) to 5 (months). Unused in 2b; it becomes the edge
    # weight for shortest-path search in Phase 3, and seeding it now means the graph phase does
    # not begin with a data-entry exercise across 120 rows.
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("3"))

    # Some skill names are ordinary English words: Go, R, C, D, Rust. Matched
    # case-insensitively they fire on "go to", "or", "a c library" — noise that would poison
    # every downstream score. These require an exact-case match instead.
    requires_exact_case: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    aliases: Mapped[list[SkillAlias]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_skills_difficulty_range"),
        CheckConstraint("slug = lower(slug)", name="ck_skills_slug_is_lowercase"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Skill {self.canonical_name!r} ({self.category.value})>"


class SkillAlias(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An alternative spelling for a skill.

    A separate table rather than an array column on `skills`, because aliases are queried,
    counted, and constrained independently — and a unique index across all aliases is what
    guarantees no two skills claim the same term, which would make matching ambiguous.
    """

    __tablename__ = "skill_aliases"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Unique across the whole table, not per skill: if "js" mapped to both JavaScript and
    # Java, extraction would be nondeterministic.
    term: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    skill: Mapped[Skill] = relationship(back_populates="aliases")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SkillAlias {self.term!r}>"
