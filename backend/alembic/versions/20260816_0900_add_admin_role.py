"""Add the admin role

Revision ID: 0009_admin_role
Revises: 0008_career_goals
Create Date: 2026-08-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_admin_role"
down_revision: str | None = "0008_career_goals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Same Postgres 12+ rule as the 'learning' status in 0008: the value may be added inside a
    # transaction, but not *used* in the same one. Nothing here promotes anyone — the first
    # admin is created deliberately, by running scripts/promote_admin.py, so that gaining the
    # highest privilege in the system is always a recorded human act rather than a side effect
    # of a deploy.
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'admin'")


def downgrade() -> None:
    # Postgres cannot drop an enum value; the type has to be rebuilt. Any existing admin is
    # demoted to job_seeker first, because the old type has no label to hold them.
    op.execute("UPDATE users SET role = 'job_seeker' WHERE role = 'admin'")
    op.execute("ALTER TYPE user_role RENAME TO user_role_old")
    op.execute("CREATE TYPE user_role AS ENUM ('job_seeker', 'recruiter')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role DROP DEFAULT, "
        "ALTER COLUMN role TYPE user_role USING role::text::user_role, "
        "ALTER COLUMN role SET DEFAULT 'job_seeker'"
    )
    op.execute("DROP TYPE user_role_old")
