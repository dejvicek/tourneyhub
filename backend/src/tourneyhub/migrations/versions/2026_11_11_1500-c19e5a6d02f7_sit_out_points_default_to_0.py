"""sit-out points default to 0, none in a round robin, no "set by hand" flag

The PRD owner's review of PR #46: in Swiss and Monster DYP the points for sitting
out default to 0 and the organizer picks 0, 1 or 2 in setup (FR-039, BR-075); a
round robin has none (BR-071). The default no longer follows the match format or
the league's draw setting, so the flag that recorded a manual pick goes.

Tournaments that exist are moved before the flag is dropped:

- a round robin's phase gets NULL;
- a Swiss or Monster DYP phase that has a result (BR-096: one of its matches has
  an outcome) keeps its value, because the value cannot change while the phase
  has a result (BR-075);
- one without a result keeps its value if the organizer picked it, and otherwise
  gets the new default, 0.

The downgrade puts the flag back as true on every group phase (each value then
counts as picked) and gives a round robin 0.

Revision ID: c19e5a6d02f7
Revises: 7b3d91c0a5e2
Create Date: 2026-11-11 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c19e5a6d02f7"
down_revision: str | None = "7b3d91c0a5e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "tournament_phases"
FLAG = "sit_out_points_set_by_hand"
CHECK = "ck_tournament_phases_sit_out_points"
FLAG_CHECK = "ck_tournament_phases_sit_out_points_set_by_hand"

_VALUE_OK = "(sit_out_points IS NULL OR sit_out_points IN (0, 1, 2))"


def upgrade() -> None:
    op.drop_constraint(op.f(CHECK), TABLE, type_="check")
    op.drop_constraint(op.f(FLAG_CHECK), TABLE, type_="check")
    op.execute(
        "UPDATE tournament_phases SET sit_out_points = NULL"
        " WHERE format = 'round_robin'"
    )
    op.execute(
        "UPDATE tournament_phases AS p SET sit_out_points = 0"
        " WHERE p.format IN ('swiss', 'monster_dyp')"
        " AND NOT p.sit_out_points_set_by_hand"
        " AND NOT EXISTS ("
        "SELECT 1 FROM matches AS m JOIN rounds AS r ON m.round_id = r.id"
        " WHERE r.phase_id = p.id AND m.outcome IS NOT NULL)"
    )
    op.drop_column(TABLE, FLAG)
    op.create_check_constraint(
        op.f(CHECK),
        TABLE,
        "(format IN ('swiss', 'monster_dyp')) = (sit_out_points IS NOT NULL)"
        f" AND {_VALUE_OK}",
    )


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK), TABLE, type_="check")
    op.add_column(
        TABLE,
        sa.Column(FLAG, sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(
        "UPDATE tournament_phases SET sit_out_points_set_by_hand = true"
        " WHERE kind = 'group'"
    )
    op.execute(
        "UPDATE tournament_phases SET sit_out_points = 0 WHERE format = 'round_robin'"
    )
    op.create_check_constraint(
        op.f(CHECK),
        TABLE,
        f"(kind = 'group') = (sit_out_points IS NOT NULL) AND {_VALUE_OK}",
    )
    op.create_check_constraint(
        op.f(FLAG_CHECK), TABLE, "NOT sit_out_points_set_by_hand OR kind = 'group'"
    )
