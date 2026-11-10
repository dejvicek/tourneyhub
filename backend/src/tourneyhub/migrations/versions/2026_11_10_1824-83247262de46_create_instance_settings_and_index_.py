"""create instance_settings and index refresh_tokens by user

DATA-MODEL §4.1: instance_settings holds one row, made here, with sign-up closed
(signup_code is NULL, ADR-007). A password change looks refresh tokens up by user.

Revision ID: 83247262de46
Revises: d057b5581002
Create Date: 2026-11-10 18:24:46.329841
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "83247262de46"
down_revision: str | None = "d057b5581002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instance_settings",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("signup_code", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name=op.f("ck_instance_settings_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instance_settings")),
    )
    op.execute("INSERT INTO instance_settings (id) VALUES (1)")
    op.create_index(
        op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("instance_settings")
