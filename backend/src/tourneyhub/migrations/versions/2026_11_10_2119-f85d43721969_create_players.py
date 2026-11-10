"""create players

DATA-MODEL §4.2: a league's player list. A name is unique within a league
ignoring case, removed players included (BR-001, ADR-002), by a unique index on
lower(name), named here like the one on users.

Revision ID: f85d43721969
Revises: f94c666342a1
Create Date: 2026-11-10 21:19:39.589002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f85d43721969"
down_revision: str | None = "f94c666342a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("league_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["league_id"],
            ["leagues.id"],
            name=op.f("fk_players_league_id_leagues"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_players")),
    )
    op.create_index(
        "uq_players_league_id_lower_name",
        "players",
        ["league_id", sa.text("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_players_league_id_lower_name", table_name="players")
    op.drop_table("players")
