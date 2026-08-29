"""Add email verification and Google Sign-In support

Revision ID: 0010_email_verification_oauth
Revises: 0009_admin_role
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_email_verification_oauth"
down_revision: str | None = "0009_admin_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users: password becomes optional, plus verification and OAuth identity -----------
    # Nullable rather than a placeholder hash: a Google-only account genuinely has no
    # password, and a schema that can say so is more honest than one that fakes one.
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)

    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("google_sub", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_users_google_sub", "users", ["google_sub"])

    # --- email_verification_tokens ---------------------------------------------------------
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_email_verification_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_email_verification_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hash", name="uq_email_verification_tokens_token_hash"),
    )
    op.create_index(
        "ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"]
    )
    op.create_index(
        "ix_email_verification_tokens_token_hash", "email_verification_tokens", ["token_hash"]
    )

    # --- back-fill: existing accounts predate this feature ---------------------------------
    # Every account already in the database registered with a password before verification
    # existed, and has presumably been using the product since. Treating them as unverified
    # would lock real users out on the next deploy for a feature that did not exist when they
    # signed up. New registrations from this point on go through the real flow.
    op.execute("UPDATE users SET email_verified_at = now() WHERE email_verified_at IS NULL")


def downgrade() -> None:
    op.drop_index("ix_email_verification_tokens_token_hash", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")

    op.drop_constraint("uq_users_google_sub", "users", type_="unique")
    op.drop_column("users", "google_sub")
    op.drop_column("users", "email_verified_at")

    # Restoring NOT NULL requires every row to have a value first. A Google-only account has
    # none, so it gets an unusable placeholder — a real Argon2 hash of random bytes that no
    # password will ever match. That account cannot sign in by password after this downgrade;
    # it could before this migration ever existed, and downgrading past the feature that made
    # password-less accounts possible is expected to lose that ability.
    # A real Argon2id hash of an unguessable string that is not, and never was, anyone's
    # actual password — generated with this project's own hasher so the format is guaranteed
    # valid and `verify_password` against it fails cleanly rather than raising on a malformed
    # string.
    op.execute(
        "UPDATE users SET password_hash = "
        "'$argon2id$v=19$m=65536,t=3,p=4$MqdBbOWWMPOz37Cfz1TEOw$"
        "5Rb//mtyNBx3faLEy3kchnS6vo4+Zk8vMirBZHERf1U' "
        "WHERE password_hash IS NULL"
    )
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
