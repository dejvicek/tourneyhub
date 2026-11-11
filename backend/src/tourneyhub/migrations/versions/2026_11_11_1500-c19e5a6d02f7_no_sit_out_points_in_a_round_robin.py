"""no sit-out points in a round robin

FR-039, BR-071: sit-out points apply only to the Swiss and Monster DYP group
phases (dejvicek's second review of PR #46). In a complete round robin every
entry sits out equally often, and with a late entry (BR-054) the points would
distort the order. A round robin's phase therefore keeps no value and no pick,
and the CHECKs say so: a Swiss or Monster DYP phase has a value, a round robin
has none.

Revision ID: c19e5a6d02f7
Revises: 7b3d91c0a5e2
Create Date: 2026-11-11 15:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c19e5a6d02f7"
down_revision: str | None = "7b3d91c0a5e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "tournament_phases"
CHECK = "ck_tournament_phases_sit_out_points"
FLAG_CHECK = "ck_tournament_phases_sit_out_points_set_by_hand"

_VALUE_OK = "(sit_out_points IS NULL OR sit_out_points IN (0, 1, 2))"


def upgrade() -> None:
    op.drop_constraint(op.f(CHECK), TABLE, type_="check")
    op.drop_constraint(op.f(FLAG_CHECK), TABLE, type_="check")
    op.execute(
        "UPDATE tournament_phases"
        " SET sit_out_points = NULL, sit_out_points_set_by_hand = false"
        " WHERE format = 'round_robin'"
    )
    op.create_check_constraint(
        op.f(CHECK),
        TABLE,
        "(format IN ('swiss', 'monster_dyp')) = (sit_out_points IS NOT NULL)"
        f" AND {_VALUE_OK}",
    )
    op.create_check_constraint(
        op.f(FLAG_CHECK),
        TABLE,
        "NOT sit_out_points_set_by_hand OR format IN ('swiss', 'monster_dyp')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK), TABLE, type_="check")
    op.drop_constraint(op.f(FLAG_CHECK), TABLE, type_="check")
    # A round robin gets 0 back, as a pick, so a later change of the league's draw
    # setting does not move it.
    op.execute(
        "UPDATE tournament_phases"
        " SET sit_out_points = 0, sit_out_points_set_by_hand = true"
        " WHERE format = 'round_robin'"
    )
    op.create_check_constraint(
        op.f(CHECK),
        TABLE,
        f"(kind = 'group') = (sit_out_points IS NOT NULL) AND {_VALUE_OK}",
    )
    op.create_check_constraint(
        op.f(FLAG_CHECK), TABLE, "NOT sit_out_points_set_by_hand OR kind = 'group'"
    )
