"""Add jobs and job_skills

Revision ID: 0005_jobs
Revises: 0004_skills
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_jobs"
down_revision: str | None = "0004_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column(
            "id", sa.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("created_by", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_jobs_created_by_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_jobs_title_not_blank"),
        sa.CheckConstraint("length(description) >= 30", name="ck_jobs_description_min_length"),
    )
    op.create_index("ix_jobs_created_by", "jobs", ["created_by"])
    op.create_index("ix_jobs_is_public", "jobs", ["is_public"])

    op.create_table(
        "job_skills",
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("importance", sa.SmallInteger(), server_default=sa.text("3"), nullable=False),
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
        sa.PrimaryKeyConstraint("job_id", "skill_id", name="pk_job_skills"),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_job_skills_job_id_jobs", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_job_skills_skill_id_skills", ondelete="CASCADE"
        ),
        sa.CheckConstraint("importance BETWEEN 1 AND 5", name="ck_job_skills_importance_range"),
    )


def downgrade() -> None:
    op.drop_table("job_skills")
    op.drop_index("ix_jobs_is_public", table_name="jobs")
    op.drop_index("ix_jobs_created_by", table_name="jobs")
    op.drop_table("jobs")
