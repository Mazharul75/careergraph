"""Add skill_edges and seed the prerequisite graph

Revision ID: 0007_skill_edges
Revises: 0006_embeddings
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.data.skill_edges_seed import SEED_EDGES, validate_edges

revision: str = "0007_skill_edges"
down_revision: str | None = "0006_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skill_edges",
        sa.Column("prerequisite_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.UUID(as_uuid=True), nullable=False),
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
        sa.PrimaryKeyConstraint("prerequisite_id", "skill_id", name="pk_skill_edges"),
        sa.ForeignKeyConstraint(
            ["prerequisite_id"],
            ["skills.id"],
            name="fk_skill_edges_prerequisite_id_skills",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_skill_edges_skill_id_skills", ondelete="CASCADE"
        ),
        sa.CheckConstraint("prerequisite_id <> skill_id", name="ck_skill_edges_no_self_loop"),
    )
    # Traversal always asks "what does this skill depend on?", so the reverse lookup needs its
    # own index — the composite primary key only serves lookups by prerequisite.
    op.create_index("ix_skill_edges_skill_id", "skill_edges", ["skill_id"])

    # Validate BEFORE inserting. A cycle in the seed data would produce a graph with no
    # topological ordering, and the failure would surface as silently wrong learning advice
    # rather than an error. Failing the migration is the loud alternative.
    validate_edges()

    connection = op.get_bind()
    ids = {
        slug: skill_id
        for skill_id, slug in connection.execute(sa.text("SELECT id, slug FROM skills")).all()
    }
    connection.execute(
        sa.text(
            "INSERT INTO skill_edges (prerequisite_id, skill_id) VALUES (:prerequisite_id, :skill_id)"
        ),
        [
            {"prerequisite_id": ids[prerequisite], "skill_id": ids[skill]}
            for prerequisite, skill in SEED_EDGES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_skill_edges_skill_id", table_name="skill_edges")
    op.drop_table("skill_edges")
