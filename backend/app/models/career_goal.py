"""A declared target role — what turns a one-off report into a journey.

Without this table the product can only answer "how do you compare to this job *right now*".
It has no memory, so nothing a user does can ever be seen to pay off, and there is no reason
to come back. Storing the score at the moment the goal was set is what makes progress
*measurable*: the difference between then and now is the whole point.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.job import Job


class CareerGoal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One user aiming at one job.

    A user has at most one *active* goal at a time — enforced by the database, not by hope
    (see ``__table_args__``). Achieved goals are kept forever as history, which is what lets
    the profile show "3 goals reached" rather than only ever the current one.
    """

    __tablename__ = "career_goals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        # Deleting the target job removes the goal. A goal pointing at nothing cannot be
        # scored, and keeping a dangling row would mean every read has to defend against it.
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The match score the moment this goal was set, frozen. Recomputing a "baseline" later is
    # impossible — the user's skills have changed by then, which is precisely the thing being
    # measured. Storing it is the only way to answer "how far have I come?"
    baseline_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Null while the goal is live. Set when the user reaches the target, which both stops it
    # being the active goal and preserves it as an achievement.
    achieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[Job] = relationship(lazy="joined")

    __table_args__ = (
        # A **partial unique index**: unique over user_id, but only across rows where
        # achieved_at IS NULL. So a user may hold exactly one active goal while accumulating
        # any number of completed ones. Expressing "one active per user" as a plain unique
        # constraint is impossible; doing it in application code means two concurrent requests
        # can both pass the check and both insert.
        Index(
            "uq_career_goals_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("achieved_at IS NULL"),
        ),
    )

    @property
    def is_active(self) -> bool:
        return self.achieved_at is None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = "achieved" if self.achieved_at else "active"
        return f"<CareerGoal user={self.user_id} job={self.job_id} {state}>"
