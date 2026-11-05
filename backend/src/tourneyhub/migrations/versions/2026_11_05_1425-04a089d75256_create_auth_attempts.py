"""create auth_attempts

Revision ID: 04a089d75256
Revises: 4afca2c6323b
Create Date: 2026-11-05 14:25:46.891980
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "04a089d75256"
down_revision: str | None = "4afca2c6323b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "login_email",
                "login_ip",
                "signup_ip",
                name="auth_attempt_kind",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            nullable=False,
        ),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_attempts")),
    )
    op.create_index(
        "ix_auth_attempts_kind_key_created_at",
        "auth_attempts",
        ["kind", "key", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_auth_attempts_kind_key_created_at", table_name="auth_attempts")
    op.drop_table("auth_attempts")
