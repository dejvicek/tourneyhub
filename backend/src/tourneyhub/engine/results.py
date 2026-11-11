"""What a match result is worth: group-phase points and a result checked against its format.

Group-phase points are shared by Swiss and Monster DYP (BR-070, BR-074). The organizer
sends a whole result, every game played or a walkover with its winner (ADR-008, BR-090
to BR-092, BR-120 to BR-124); a walkover needs no check here (BR-124), everything else
becomes the match's outcome through `match_outcome`.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from tourneyhub.engine.errors import (
    DrawNotAllowedError,
    GameScoreMismatchError,
    ResultDoesNotFitFormatError,
    ScoresRequiredError,
)
from tourneyhub.engine.tournaments import MatchFormat, MatchOutcome, Outcome

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


MAX_GAMES = 5
"""BO5 plays at most five games (BR-121)."""

GAMES_TO_WIN = {MatchFormat.BO1: 1, MatchFormat.BO3: 2, MatchFormat.BO5: 3}
"""The games a side needs to win the match; BO2 always plays two (BR-121)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Game:
    """One game as the organizer enters it (FR-050, FR-051).

    Attributes:
        winner: The side that won the game, or a draw.
        score_1: Side 1's goals, or None without a score.
        score_2: Side 2's goals, or None without a score.
    """

    winner: Outcome
    score_1: int | None = None
    score_2: int | None = None


def _check_scores(games: Sequence[Game], *, scores_required: bool) -> None:
    for game_no, game in enumerate(games, start=1):
        if game.score_1 is None or game.score_2 is None:
            if game.score_1 is not None or game.score_2 is not None:
                raise GameScoreMismatchError(game_no=game_no)
            if scores_required:
                raise ScoresRequiredError(game_no=game_no)
            continue
        if not _agrees(game.winner, game.score_1, game.score_2):
            raise GameScoreMismatchError(game_no=game_no)


def _agrees(winner: Outcome, score_1: int, score_2: int) -> bool:
    if winner is Outcome.SIDE_1:
        return score_1 > score_2
    if winner is Outcome.SIDE_2:
        return score_2 > score_1
    return score_1 == score_2


def match_outcome(
    games: Sequence[Game],
    *,
    match_format: MatchFormat,
    draws_allowed: bool,
    scores_required: bool,
) -> Outcome:
    """Return the outcome the games make in `match_format` (BR-090 to BR-092, BR-121).

    - **BO1:** exactly one game; its winner is the match's, and a drawn game
      is a drawn match.
    - **BO2:** exactly two games, neither drawn; 2:0 wins, 1:1 is a draw.
    - **BO3, BO5:** no drawn game; the first side to win 2 or 3 games wins,
      and no game follows the one that decides it.

    Scores are optional per game, but both or neither, and the winner must
    have the higher score, a drawn game equal ones (BR-092). Goals per game
    is a guide, not a rule, so any whole number counts (BR-123).

    Args:
        games: The games in the order they were played.
        match_format: The match's format: its phase's, or the final's own (BR-120).
        draws_allowed: The match is in a group phase of a league that allows
            draws (BR-090).
        scores_required: Every game needs its score: Swiss and Monster DYP
            rounds (BR-092).

    Raises:
        GameScoreMismatchError: A game has one score, or its winner did not
            score more (or, drawn, the same).
        ScoresRequiredError: A game has no score where every game needs one.
        DrawNotAllowedError: The result is a draw where draws are not allowed.
        ResultDoesNotFitFormatError: The games do not make a result in the
            format.
    """
    _check_scores(games, scores_required=scores_required)
    unfit = ResultDoesNotFitFormatError(match_format=match_format, games=len(games))
    if match_format is MatchFormat.BO1:
        if len(games) != 1:
            raise unfit
        outcome = games[0].winner
    else:
        if any(game.winner is Outcome.DRAW for game in games):
            raise unfit
        outcome = _series_outcome(games, match_format=match_format, unfit=unfit)
    if outcome is Outcome.DRAW and not draws_allowed:
        raise DrawNotAllowedError
    return outcome


def _series_outcome(
    games: Sequence[Game],
    *,
    match_format: MatchFormat,
    unfit: ResultDoesNotFitFormatError,
) -> Outcome:
    """The outcome of BO2, BO3 or BO5 games, none of them drawn (BR-121)."""
    wins = Counter(game.winner for game in games)
    if match_format is MatchFormat.BO2:
        if len(games) != 2:  # noqa: PLR2004  (BO2 is two games by definition)
            raise unfit
        return wins.most_common(1)[0][0] if len(wins) == 1 else Outcome.DRAW
    need = GAMES_TO_WIN[match_format]
    won = Counter[Outcome]()
    for game in games:
        if max(won.values(), default=0) == need:
            raise unfit  # a game after the series was decided
        won[game.winner] += 1
    leader, most = won.most_common(1)[0] if won else (Outcome.DRAW, 0)
    if most != need:
        raise unfit
    return leader
