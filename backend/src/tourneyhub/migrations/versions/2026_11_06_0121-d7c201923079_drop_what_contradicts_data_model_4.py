"""drop what contradicts DATA-MODEL §4

DATA-MODEL §4.2 has no unique league name and no leagues.status; §4.1 makes
users.email unique on lower(email) (FR-002).

Revision ID: d7c201923079
Revises: ed88a108889a
Create Date: 2026-11-06 01:21:56.562416
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7c201923079"
down_revision: str | None = "ed88a108889a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("uq_leagues_owner_user_id_name"), "leagues", type_="unique")
    op.drop_constraint(op.f("ck_leagues_league_status"), "leagues", type_="check")
    op.drop_column("leagues", "status")
    # An expression index has no name from the naming convention.
    op.create_index(
        "uq_users_lower_email", "users", [sa.text("lower(email)")], unique=True
    )
    op.drop_constraint(op.f("uq_users_email"), "users", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(op.f("uq_users_email"), "users", ["email"])
    op.drop_index("uq_users_lower_email", table_name="users")
    # Existing leagues become active, the status every league was created with.
    op.add_column(
        "leagues",
        sa.Column("status", sa.String(), server_default="active", nullable=False),
    )
    op.alter_column(
        "leagues",
        "status",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default=None,
    )
    op.create_check_constraint(
        op.f("ck_leagues_league_status"), "leagues", "status IN ('active', 'archived')"
    )
    # Fails if an organizer has two leagues of one name, which only this
    # revision allows.
    op.create_unique_constraint(
        op.f("uq_leagues_owner_user_id_name"), "leagues", ["owner_user_id", "name"]
    )
