"""Job descriptions.

One table serves both PRD user stories. A job seeker pastes a posting they found elsewhere as a
private target to measure themselves against; a recruiter publishes a posting that candidates
can be ranked for. The row is identical either way — a title and a description with required
skills — so `is_public` distinguishes them rather than a second near-duplicate table.
"""

from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.skill import Skill
from app.services.embedding import EMBEDDING_DIMENSIONS


class Job(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "jobs"

    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Only recruiters may set this. A public posting is visible to every user and becomes a
    # candidate-ranking target in Phase 2c; a private one is a personal benchmark.
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), index=True
    )

    # Written asynchronously by the worker. Null until the embedding task runs, which is why
    # scoring falls back to skills-only rather than refusing to answer.
    embedding: Mapped[list[float] | None] = deferred(
        mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    )

    required_skills: Mapped[list[JobSkill]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_jobs_title_not_blank"),
        CheckConstraint("length(description) >= 30", name="ck_jobs_description_min_length"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Job {self.title!r} public={self.is_public}>"


class JobSkill(Base, TimestampMixin):
    """A skill a job requires, with how much it matters."""

    __tablename__ = "job_skills"

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )

    # 1-5. Derived from how often the skill appears in the description: a technology named
    # once in a "nice to have" list matters less than one named in four bullet points. Crude,
    # but honest and explainable — and it becomes the weighting term in the Phase 2c match
    # score, so an unexplainable heuristic here would make the score unexplainable too.
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("3"))

    job: Mapped[Job] = relationship(back_populates="required_skills")
    skill: Mapped[Skill] = relationship(lazy="joined")

    __table_args__ = (
        PrimaryKeyConstraint("job_id", "skill_id", name="pk_job_skills"),
        CheckConstraint("importance BETWEEN 1 AND 5", name="ck_job_skills_importance_range"),
    )
