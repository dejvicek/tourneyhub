"""take created_at from the application clock

Revision ID: ecb95f17d71d
Revises: 04a089d75256
Create Date: 2026-11-05 14:59:50.394172
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ecb95f17d71d"
down_revision: str | None = "04a089d75256"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "auth_attempts",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "leagues",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=None,
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "leagues",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "auth_attempts",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
