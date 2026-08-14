"""Add embedding columns and vector indexes

Revision ID: 0006_embeddings
Revises: 0005_jobs
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0006_embeddings"
down_revision: str | None = "0005_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# BAAI/bge-small-en-v1.5. Fixed in the schema: changing embedding models means every stored
# vector is meaningless, so a dimension change is a migration, not a config tweak.
DIMENSIONS = 384


def upgrade() -> None:
    # The `vector` extension was enabled by migration 0001, before there was anything to use
    # it for — deliberately, so pgvector availability was proven on day one rather than
    # discovered to be missing on the day it was first needed.
    op.add_column("resumes", sa.Column("embedding", Vector(DIMENSIONS), nullable=True))
    op.add_column("jobs", sa.Column("embedding", Vector(DIMENSIONS), nullable=True))

    # HNSW (Hierarchical Navigable Small World) is an approximate-nearest-neighbour index.
    # Without it, "find the closest job to this resume" scans every row and computes distance
    # for each — fine at our size, ruinous later. Approximate: it can miss a true nearest
    # neighbour, which is an acceptable trade for sublinear search.
    #
    # `vector_cosine_ops` must match the operator used at query time (`<=>`, cosine distance).
    # An index built for L2 distance simply will not be used by a cosine query — the query
    # silently falls back to a sequential scan, which is the classic way a vector index gets
    # built and then never used.
    op.execute(
        "CREATE INDEX ix_resumes_embedding_hnsw ON resumes USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_jobs_embedding_hnsw ON jobs USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_resumes_embedding_hnsw")
    op.drop_column("jobs", "embedding")
    op.drop_column("resumes", "embedding")
