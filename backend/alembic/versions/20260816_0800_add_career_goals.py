"""Add career_goals and the 'learning' skill status

Revision ID: 0008_career_goals
Revises: 0007_skill_edges
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_career_goals"
down_revision: str | None = "0007_skill_edges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- New skill status ---------------------------------------------------------------
    # `ALTER TYPE ... ADD VALUE` historically could not run inside a transaction block, and
    # Alembic wraps every migration in one. Postgres 12+ permits it, with one restriction:
    # the new value cannot be *used* in the same transaction that adds it. Nothing here
    # inserts a 'learning' row, so this is safe — but a later migration that back-fills rows
    # to 'learning' must be a separate revision, not appended to this one.
    op.execute("ALTER TYPE skill_status ADD VALUE IF NOT EXISTS 'learning'")

    # --- Career goals -------------------------------------------------------------------
    op.create_table(
        "career_goals",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_score", sa.Float(), nullable=False),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_career_goals"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_career_goals_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_career_goals_job_id_jobs", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "baseline_score >= 0 AND baseline_score <= 100",
            name="ck_career_goals_baseline_score_range",
        ),
    )
    op.create_index("ix_career_goals_user_id", "career_goals", ["user_id"])
    op.create_index("ix_career_goals_job_id", "career_goals", ["job_id"])

    # One *active* goal per user, enforced in the database. A partial index is the only way to
    # say this: a plain unique constraint on user_id would also forbid a second completed goal,
    # and checking in Python loses to two concurrent requests.
    op.create_index(
        "uq_career_goals_one_active_per_user",
        "career_goals",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("achieved_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_career_goals_one_active_per_user", table_name="career_goals")
    op.drop_index("ix_career_goals_job_id", table_name="career_goals")
    op.drop_index("ix_career_goals_user_id", table_name="career_goals")
    op.drop_table("career_goals")

    # Postgres cannot remove a value from an enum. Rebuilding the type is the only way, and
    # it must happen in dependency order: detach the column, swap the type, reattach.
    #
    # Any row already sitting at 'learning' would violate the new type, so those are folded
    # back to 'suggested' first — the closest honest equivalent, since both mean "not yet
    # counted as held".
    op.execute("UPDATE user_skills SET status = 'suggested' WHERE status = 'learning'")
    op.execute("ALTER TYPE skill_status RENAME TO skill_status_old")
    op.execute("CREATE TYPE skill_status AS ENUM ('suggested', 'confirmed', 'rejected')")
    op.execute(
        "ALTER TABLE user_skills ALTER COLUMN status TYPE skill_status "
        "USING status::text::skill_status"
    )
    op.execute("DROP TYPE skill_status_old")
