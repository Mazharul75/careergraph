"""A user's skill profile — the correctable output of extraction."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, PrimaryKeyConstraint, SmallInteger
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.skill import Skill


class SkillSource(enum.StrEnum):
    """Where the claim came from."""

    EXTRACTED = "extracted"  # found in resume text by the matcher
    MANUAL = "manual"  # the user added it themselves


class SkillStatus(enum.StrEnum):
    """What the user has decided about it.

    ``REJECTED`` rows are kept rather than deleted, and that is the important design choice
    here. Extraction is not perfect and re-running it is routine — every resume upload re-runs
    it. If a rejection were a deleted row, the next parse would resurrect the same wrong skill
    and the user would have to dismiss it again, forever. A tombstone makes the correction
    stick.
    """

    SUGGESTED = "suggested"  # extracted, awaiting confirmation
    CONFIRMED = "confirmed"  # the user agreed, or added it manually
    REJECTED = "rejected"  # the user said no — do not suggest again


class UserSkill(Base, TimestampMixin):
    """Join row between a user and a skill.

    Composite primary key on (user_id, skill_id): a user holds a given skill at most once, and
    the database enforces it rather than the application hoping.
    """

    __tablename__ = "user_skills"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )

    source: Mapped[SkillSource] = mapped_column(
        Enum(
            SkillSource,
            name="skill_source",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[SkillStatus] = mapped_column(
        Enum(
            SkillStatus,
            name="skill_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )

    # Self-assessed, 1-5, null until the user says. Never inferred from a resume: appearing in
    # a bullet point says nothing about depth, and guessing would put a number in front of the
    # user that they did not choose and cannot defend in an interview.
    proficiency: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # How many times the term appeared in the resume. A weak but real signal — a skill named
    # once in a list is different from one named in four bullet points — and useful for
    # ordering suggestions in the UI.
    occurrences: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    skill: Mapped[Skill] = relationship(lazy="joined")

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "skill_id", name="pk_user_skills"),
        CheckConstraint(
            "proficiency IS NULL OR proficiency BETWEEN 1 AND 5",
            name="ck_user_skills_proficiency_range",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<UserSkill user={self.user_id} skill={self.skill_id} {self.status.value}>"
