from collections.abc import Sequence
from enum import StrEnum


class SeasonState(StrEnum):
    """Whether a season is the league's active one (FR-021, DATA-MODEL §4.2)."""

    ACTIVE = "active"
    CLOSED = "closed"


class DefaultMatchFormat(StrEnum):
    """The match format a league's new tournaments start with (FR-011, BR-120).

    Not BO2: only group phases of leagues with draws can play it (BR-121), so a
    default that a knockout cannot take is never copied (DATA-MODEL §4.2).
    """

    BO1 = "bo1"
    BO3 = "bo3"
    BO5 = "bo5"


DEFAULT_PLACEMENT_POINTS: tuple[int, ...] = (10, 8, 6, 4, 2)
"""The placement points table of a new league's Season 1 (FR-011)."""


MAX_FIELD_COUNT = 32
"""The most fields a league default, and later a tournament, may name (DATA-MODEL §4.2)."""

MAX_PLAYERS_PER_LEAGUE = 500
"""The most players a league may hold, removed ones included (DATA-MODEL §4.2).

Removed players keep their rows and their names, so they count.

BR-006 now says 1000 active players, removed ones not counted, and restores count
again. The change is the #48 follow-up (issue to open after approval).
"""

MAX_GOALS_PER_GAME = 99
"""The most goals per game a league default may name (DATA-MODEL §4.2)."""


def first_increase(points: Sequence[int]) -> int | None:
    """Return the index of the first place worth more than the place above it.

    FR-011: no place is worth more than the place above it, so a valid table
    returns None. The database's `placement_points_valid()` checks the same.
    """
    return next(
        (index for index in range(1, len(points)) if points[index] > points[index - 1]),
        None,
    )
