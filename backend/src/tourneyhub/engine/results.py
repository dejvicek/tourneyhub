"""What a group-phase match earns, shared by Swiss and Monster DYP (BR-070, BR-074)."""

from enum import StrEnum

from tourneyhub.engine.tournaments import MatchOutcome

WIN_POINTS = 2
"""Points for a win in a group phase; a loss earns 0 (BR-070)."""

DRAW_POINTS = 1
"""Points for a draw in a group phase (BR-070)."""


class Result(StrEnum):
    """A match from one side's view."""

    WON = "won"
    DRAWN = "drawn"
    LOST = "lost"


POINTS = {Result.WON: WIN_POINTS, Result.DRAWN: DRAW_POINTS, Result.LOST: 0}
"""The points each result earns (BR-070)."""


def result_for(outcome: MatchOutcome, own: MatchOutcome) -> Result:
    """Return a match's result from the view of the side `own`."""
    if outcome is MatchOutcome.DRAW:
        return Result.DRAWN
    return Result.WON if outcome is own else Result.LOST


def tiebreak_purpose(completed_rounds: int) -> str:
    """Name the lot of BR-074, `tiebreak:after-round-<completed_rounds>` (ADR-010).

    The number of completed rounds is part of the purpose, so tied players are
    ordered afresh after each round, and the same way on every read.
    """
    return f"tiebreak:after-round-{completed_rounds}"
