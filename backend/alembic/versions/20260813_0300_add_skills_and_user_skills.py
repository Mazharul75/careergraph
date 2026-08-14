"""Add skills, skill_aliases, user_skills and seed the vocabulary

Revision ID: 0004_skills
Revises: 0003_resumes
Create Date: 2026-08-13

The seed data lives in the migration rather than a separate script, because the vocabulary is
*reference data the schema is useless without* — an empty `skills` table means extraction
silently finds nothing. Putting it here means a fresh database on a laptop, in CI, and on Neon
all arrive at the same 113 skills with no extra step for anyone to forget.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.data.skills_seed import SEED_SKILLS

revision: str = "0004_skills"
down_revision: str | None = "0003_resumes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    skill_category = postgresql.ENUM(
        "language",
        "framework",
        "database",
        "infrastructure",
        "data_ml",
        "tool",
        "concept",
        name="skill_category",
        create_type=False,
    )
    skill_source = postgresql.ENUM("extracted", "manual", name="skill_source", create_type=False)
    skill_status = postgresql.ENUM(
        "suggested", "confirmed", "rejected", name="skill_status", create_type=False
    )
    for enum_type in (skill_category, skill_source, skill_status):
        enum_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "skills",
        sa.Column(
            "id", sa.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("canonical_name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("category", skill_category, nullable=False),
        sa.Column("difficulty", sa.SmallInteger(), server_default=sa.text("3"), nullable=False),
        sa.Column(
            "requires_exact_case", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_skills"),
        sa.UniqueConstraint("canonical_name", name="uq_skills_canonical_name"),
        sa.UniqueConstraint("slug", name="uq_skills_slug"),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_skills_difficulty_range"),
        sa.CheckConstraint("slug = lower(slug)", name="ck_skills_slug_is_lowercase"),
    )
    op.create_index("ix_skills_canonical_name", "skills", ["canonical_name"])
    op.create_index("ix_skills_slug", "skills", ["slug"])
    op.create_index("ix_skills_category", "skills", ["category"])

    op.create_table(
        "skill_aliases",
        sa.Column(
            "id", sa.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("skill_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("term", sa.String(length=100), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_skill_aliases"),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_skill_aliases_skill_id_skills", ondelete="CASCADE"
        ),
        # Unique across the entire table, not per skill. If "js" mapped to both JavaScript and
        # Java, extraction would depend on iteration order.
        sa.UniqueConstraint("term", name="uq_skill_aliases_term"),
    )
    op.create_index("ix_skill_aliases_skill_id", "skill_aliases", ["skill_id"])
    op.create_index("ix_skill_aliases_term", "skill_aliases", ["term"])

    op.create_table(
        "user_skills",
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("source", skill_source, nullable=False),
        sa.Column("status", skill_status, nullable=False),
        sa.Column("proficiency", sa.SmallInteger(), nullable=True),
        sa.Column("occurrences", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
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
        # Composite key: a user holds a given skill at most once, enforced by the database.
        sa.PrimaryKeyConstraint("user_id", "skill_id", name="pk_user_skills"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_skills_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_user_skills_skill_id_skills", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "proficiency IS NULL OR proficiency BETWEEN 1 AND 5",
            name="ck_user_skills_proficiency_range",
        ),
    )
    op.create_index("ix_user_skills_status", "user_skills", ["status"])

    _seed_vocabulary()


def _seed_vocabulary() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            "INSERT INTO skills (canonical_name, slug, category, difficulty, requires_exact_case) "
            "VALUES (:canonical_name, :slug, CAST(:category AS skill_category), :difficulty, :requires_exact_case)"
        ),
        [
            {
                "canonical_name": skill.canonical_name,
                "slug": skill.slug,
                "category": skill.category,
                "difficulty": skill.difficulty,
                "requires_exact_case": skill.exact_case,
            }
            for skill in SEED_SKILLS
        ],
    )

    # Read the generated ids back rather than pre-generating UUIDs in Python: the column's
    # server default stays the single source of truth for how ids are made.
    ids = {
        slug: skill_id
        for skill_id, slug in connection.execute(sa.text("SELECT id, slug FROM skills")).all()
    }

    alias_rows = [
        {"skill_id": ids[skill.slug], "term": term}
        for skill in SEED_SKILLS
        for term in skill.aliases
    ]
    if alias_rows:
        connection.execute(
            sa.text("INSERT INTO skill_aliases (skill_id, term) VALUES (:skill_id, :term)"),
            alias_rows,
        )


def downgrade() -> None:
    op.drop_index("ix_user_skills_status", table_name="user_skills")
    op.drop_table("user_skills")
    op.drop_index("ix_skill_aliases_term", table_name="skill_aliases")
    op.drop_index("ix_skill_aliases_skill_id", table_name="skill_aliases")
    op.drop_table("skill_aliases")
    op.drop_index("ix_skills_category", table_name="skills")
    op.drop_index("ix_skills_slug", table_name="skills")
    op.drop_index("ix_skills_canonical_name", table_name="skills")
    op.drop_table("skills")
    for name in ("skill_status", "skill_source", "skill_category"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
