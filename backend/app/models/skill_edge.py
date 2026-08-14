"""Prerequisite edges — the persisted form of the skill graph.

This table *is* the graph. NetworkX loads from it into memory for traversal; it is not a second
copy that could drift. Postgres owns the data, NetworkX owns the algorithms.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SkillEdge(Base, TimestampMixin):
    """``prerequisite_id → skill_id``: learn the prerequisite first."""

    __tablename__ = "skill_edges"

    prerequisite_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        # The composite key makes the edge set a true set: the same prerequisite cannot be
        # declared twice, which would double-count effort in a plan.
        PrimaryKeyConstraint("prerequisite_id", "skill_id", name="pk_skill_edges"),
        # A self-loop is a one-node cycle, and the cheapest cycle to rule out in SQL. Longer
        # cycles cannot be expressed as a CHECK — they are caught by the seed validator and by
        # `build_graph` at load time.
        CheckConstraint("prerequisite_id <> skill_id", name="ck_skill_edges_no_self_loop"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SkillEdge {self.prerequisite_id} -> {self.skill_id}>"
