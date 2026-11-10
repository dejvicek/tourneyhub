"""add user profile columns and refresh_tokens

DATA-MODEL §4.1: users gets display_name, password_hash, language and its
timestamps; refresh_tokens holds the rotating refresh tokens (ADR-006).

Rows that exist already get a display name from their email, the language en,
created_at of the migration and the password hash "!", which no password
matches: an admin sets their password (FR-006).

Revision ID: d057b5581002
Revises: d7c201923079
Create Date: 2026-11-10 16:19:59.780902
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d057b5581002"
down_revision: str | None = "d7c201923079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["refresh_tokens.id"],
            name=op.f("fk_refresh_tokens_parent_id_refresh_tokens"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_refresh_tokens_family_id"),
        "refresh_tokens",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_tokens_parent_id"),
        "refresh_tokens",
        ["parent_id"],
        unique=False,
    )
    # The defaults fill the rows that exist; the application sets every column.
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(), server_default="", nullable=False),
    )
    op.execute("UPDATE users SET display_name = split_part(email, '@', 1)")
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(), server_default="!", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column(
            "language",
            sa.Enum(
                "en",
                "cs",
                name="language",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            server_default="en",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "users", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    for column in ("display_name", "password_hash", "language", "created_at"):
        op.alter_column("users", column, server_default=None)


def downgrade() -> None:
    op.drop_column("users", "updated_at")
    op.drop_column("users", "created_at")
    op.drop_column("users", "language")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "display_name")
    op.drop_index(op.f("ix_refresh_tokens_parent_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
