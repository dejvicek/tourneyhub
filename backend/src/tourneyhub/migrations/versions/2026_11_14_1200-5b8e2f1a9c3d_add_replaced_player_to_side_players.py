"""a side player can be a replacement in a Lord have mercy knockout

Step 2 of issue #63: a replacement who comes into a later round of a Lord have
mercy knockout in place of a player who left is stored with the draw, on their
own row in `match_side_players`, which names the player they came in for
(BR-148, DATA-MODEL D4). Deleting the round deletes the row and so undoes the
replacement (BR-154). Existing rows have no replacement.

Revision ID: 5b8e2f1a9c3d
Revises: c19e5a6d02f7
Create Date: 2026-11-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b8e2f1a9c3d"
down_revision: str | None = "c19e5a6d02f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "match_side_players"
COLUMN = "replaced_player_id"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column(COLUMN, sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_match_side_players_replaced_player_id_players",
        TABLE,
        "players",
        [COLUMN],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
    op.create_check_constraint(
        op.f("ck_match_side_players_replaced_player"),
        TABLE,
        "replaced_player_id <> player_id",
    )
    op.create_index(
        op.f("ix_match_side_players_replaced_player_id"), TABLE, [COLUMN], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_match_side_players_replaced_player_id"), table_name=TABLE)
    op.drop_constraint(
        op.f("ck_match_side_players_replaced_player"), TABLE, type_="check"
    )
    op.drop_constraint(
        "fk_match_side_players_replaced_player_id_players", TABLE, type_="foreignkey"
    )
    op.drop_column(TABLE, COLUMN)
