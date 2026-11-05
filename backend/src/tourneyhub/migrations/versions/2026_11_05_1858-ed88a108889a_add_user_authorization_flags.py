"""add user authorization flags

Revision ID: ed88a108889a
Revises: ecb95f17d71d
Create Date: 2026-11-05 18:58:05.822756
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ed88a108889a"
down_revision: str | None = "ecb95f17d71d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "is_admin")
