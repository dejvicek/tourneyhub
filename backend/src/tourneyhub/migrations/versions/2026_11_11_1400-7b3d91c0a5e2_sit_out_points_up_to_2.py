"""sit-out points up to 2 and whether the organizer set them

FR-039, BR-071: a sit-out is worth 0, 1 or 2 points, and the default follows the
group phase's match format until the organizer picks a value. The new column
records that pick. Every group phase that exists keeps the value it has, so
those rows count as picked (setup offered 0 or 1 as an explicit choice).

Revision ID: 7b3d91c0a5e2
Revises: 4502d5926476
Create Date: 2026-11-11 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b3d91c0a5e2"
down_revision: str | None = "4502d5926476"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "tournament_phases"
CHECK = "ck_tournament_phases_sit_out_points"
FLAG_CHECK = "ck_tournament_phases_sit_out_points_set_by_hand"


def _sit_out_points_check(highest: int) -> str:
    values = ", ".join(str(n) for n in range(highest + 1))
    return (
        "(kind = 'group') = (sit_out_points IS NOT NULL)"
        f" AND (sit_out_points IS NULL OR sit_out_points IN ({values}))"
    )


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "sit_out_points_set_by_hand",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE tournament_phases SET sit_out_points_set_by_hand = true"
        " WHERE kind = 'group'"
    )
    op.create_check_constraint(
        op.f(FLAG_CHECK), TABLE, "NOT sit_out_points_set_by_hand OR kind = 'group'"
    )
    op.drop_constraint(op.f(CHECK), TABLE, type_="check")
    op.create_check_constraint(op.f(CHECK), TABLE, _sit_out_points_check(2))


def downgrade() -> None:
    # A phase that gave a sit-out 2 points has no place in the old range.
    op.execute(
        "UPDATE tournament_phases SET sit_out_points = 1 WHERE sit_out_points = 2"
    )
    op.drop_constraint(op.f(CHECK), TABLE, type_="check")
    op.create_check_constraint(op.f(CHECK), TABLE, _sit_out_points_check(1))
    op.drop_constraint(op.f(FLAG_CHECK), TABLE, type_="check")
    op.drop_column(TABLE, "sit_out_points_set_by_hand")
