"""Add resumes table

Revision ID: 0003_resumes
Revises: 0002_refresh_tokens
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_resumes"
down_revision: str | None = "0002_refresh_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    parse_status = postgresql.ENUM(
        "pending",
        "processing",
        "complete",
        "failed",
        name="parse_status",
        create_type=False,
    )
    parse_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "resumes",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", parse_status, server_default="pending", nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_resumes"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_resumes_user_id_users", ondelete="CASCADE"
        ),
        # Belt and braces against an unbounded upload reaching the database, independent of the
        # application-level limit. A constraint cannot be forgotten during a refactor.
        sa.CheckConstraint("size_bytes > 0", name="ck_resumes_size_bytes_positive"),
    )

    op.create_index("ix_resumes_user_id", "resumes", ["user_id"])
    op.create_index("ix_resumes_status", "resumes", ["status"])


def downgrade() -> None:
    op.drop_index("ix_resumes_status", table_name="resumes")
    op.drop_index("ix_resumes_user_id", table_name="resumes")
    op.drop_table("resumes")
    sa.Enum(name="parse_status").drop(op.get_bind(), checkfirst=True)
