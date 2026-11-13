"""Round-robin standings, computed on every read (BR-070, BR-071, BR-101, ADR-009)."""

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from tourneyhub.engine.ids import EntryId, ensure_distinct
from tourneyhub.engine.tournaments import MatchFormat, Outcome

WIN_POINTS = 2
"""Group-phase points for a won match (BR-070, BR-122)."""

DRAW_POINTS = 1
"""Group-phase points for a drawn match (BR-070, BR-122)."""

FORM_LENGTH = 5
"""How many of an entry's latest results its form shows."""

WALKOVER_GAMES = {
    MatchFormat.BO1: 1,
    MatchFormat.BO2: 2,
    MatchFormat.BO3: 2,
    MatchFormat.BO5: 3,
}
"""The games a walkover counts for its winner, those needed to win (BR-101)."""


class FormResult(StrEnum):
    """One result in an entry's form, from the entry's side."""

    WON = "won"
    DRAWN = "drawn"
    LOST = "lost"


class RoundRobinTiebreaker(StrEnum):
    """What ranks an entry above another level on points (BR-101)."""

    HEAD_TO_HEAD = "head_to_head"
    GAME_DIFFERENCE = "game_difference"
    SCORE_DIFFERENCE = "score_difference"


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayedMatch:
    """A match with a result, as the standings read it.

    Attributes:
        side_1: The entry on side 1.
        side_2: The entry on side 2.
        outcome: The result; a walkover is a normal win and loss (BR-093).
        games: The winner of each game played, or a draw; empty for a
            walkover.
        is_walkover: The match was a walkover: its winner counts the games
            needed to win the format (BR-101, `WALKOVER_GAMES`).
        scores: The goals of each game that has a score, side 1 first.
            Games without one count for nothing in the score difference
            (BR-101).
    """

    side_1: EntryId
    side_2: EntryId
    outcome: Outcome
    games: tuple[Outcome, ...] = ()
    is_walkover: bool = False
    scores: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class StandingRow:
    """One entry's line in the standings (BR-101, FR-060).

    Attributes:
        place: 1 for the best. Entries still level share the place, and the
            next place skips as many as they are (BR-074, BR-104).
        entry_id: The entry.
        played: Matches with a result.
        won: Matches won, walkovers included (BR-093).
        drawn: Matches drawn.
        lost: Matches lost.
        sat_out: Rounds sat out (BR-051).
        points: 2 per win and 1 per draw (BR-070); a round sat out earns none
            in a round robin (BR-071).
        game_difference: Games won minus games lost; a drawn game counts as
            neither, and a walkover as the games needed to win (BR-101).
        score_difference: Goals for minus goals against, over the games with
            a score (BR-101).
        form: The entry's latest results, at most `FORM_LENGTH`, oldest first.
        ahead_by: What ranks this entry above the next one when both are
            level on points; None when points decide or the place is shared.
    """

    place: int
    entry_id: EntryId
    played: int
    won: int
    drawn: int
    lost: int
    sat_out: int
    points: int
    game_difference: int
    score_difference: int
    form: tuple[FormResult, ...]
    ahead_by: RoundRobinTiebreaker | None


@dataclass(frozen=True, slots=True, kw_only=True)
class _Tally:
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    sat_out: int = 0
    points: int = 0
    game_difference: int = 0
    score_difference: int = 0


def _result_for(outcome: Outcome, *, side: Outcome) -> FormResult:
    if outcome is Outcome.DRAW:
        return FormResult.DRAWN
    return FormResult.WON if outcome is side else FormResult.LOST


_POINTS = {
    FormResult.WON: WIN_POINTS,
    FormResult.DRAWN: DRAW_POINTS,
    FormResult.LOST: 0,
}


def round_robin_standings(
    entries: Iterable[EntryId],
    *,
    matches: Iterable[PlayedMatch],
    match_format: MatchFormat,
    sit_outs: Iterable[EntryId] = (),
) -> tuple[StandingRow, ...]:
    """Rank a round robin's entries (BR-070, BR-101).

    Entries are ranked by the points of their matches (BR-070); a sit-out earns
    none here, only Swiss and Monster DYP score one (BR-071): in a complete
    round robin every entry sits out equally often, and with a late entry
    (BR-054) the points would distort the order. A sit-out is still counted.
    Entries are ranked by points. When exactly two entries are level on
    points, the one with more points from the matches between them ranks
    higher; entries still level, and three or more level on points, are
    ordered by game difference, then by score difference, and after that
    share the place (BR-074). This order applies in every match format.
    Entries sharing a place keep the order they are given in, so pass them
    by seed.

    Args:
        entries: Every entry of the round robin, in seed order.
        matches: The matches with a result, in schedule order; the form
            follows this order.
        match_format: The phase's match format, for the games a walkover
            counts (BR-101).
        sit_outs: One item per round an entry sat out (BR-051); the caller
            decides which rounds count. They are counted, not scored.

    Returns:
        One row per entry, best first.

    Raises:
        ValueError: A caller bug: an entry is given twice, a match or a
            sit-out names an unknown entry, a match has one entry on both
            sides, or a walkover is a draw.
    """
    order = tuple(entries)
    ensure_distinct(order)
    tallies = {entry_id: _Tally() for entry_id in order}
    forms: dict[EntryId, list[FormResult]] = {entry_id: [] for entry_id in order}
    meetings: defaultdict[frozenset[EntryId], Counter[EntryId]] = defaultdict(Counter)

    def tally(entry_id: EntryId) -> _Tally:
        try:
            return tallies[entry_id]
        except KeyError:
            msg = f"entry {entry_id} is not among the entries"
            raise ValueError(msg) from None

    for match in matches:
        if match.side_1 == match.side_2:
            msg = f"entry {match.side_1} plays on both sides"
            raise ValueError(msg)
        goals = sum(score_1 - score_2 for score_1, score_2 in match.scores)
        games = _game_difference(match, match_format)
        meeting = meetings[frozenset((match.side_1, match.side_2))]
        for entry_id, side, difference, game_difference in (
            (match.side_1, Outcome.SIDE_1, goals, games),
            (match.side_2, Outcome.SIDE_2, -goals, -games),
        ):
            row = tally(entry_id)
            result = _result_for(match.outcome, side=side)
            tallies[entry_id] = replace(
                row,
                played=row.played + 1,
                won=row.won + (result is FormResult.WON),
                drawn=row.drawn + (result is FormResult.DRAWN),
                lost=row.lost + (result is FormResult.LOST),
                points=row.points + _POINTS[result],
                game_difference=row.game_difference + game_difference,
                score_difference=row.score_difference + difference,
            )
            forms[entry_id].append(result)
            meeting[entry_id] += _POINTS[result]
    for entry_id in sit_outs:
        row = tally(entry_id)
        tallies[entry_id] = replace(row, sat_out=row.sat_out + 1)

    ranked = _rank(order, tallies, meetings)
    rows: list[StandingRow] = []
    for entry_id, place, ahead_by in ranked:
        row = tallies[entry_id]
        rows.append(
            StandingRow(
                place=place,
                entry_id=entry_id,
                played=row.played,
                won=row.won,
                drawn=row.drawn,
                lost=row.lost,
                sat_out=row.sat_out,
                points=row.points,
                game_difference=row.game_difference,
                score_difference=row.score_difference,
                form=tuple(forms[entry_id][-FORM_LENGTH:]),
                ahead_by=ahead_by,
            )
        )
    return tuple(rows)


def _game_difference(match: PlayedMatch, match_format: MatchFormat) -> int:
    """Side 1's games won minus games lost in one match (BR-101)."""
    if match.is_walkover:
        if match.outcome is Outcome.DRAW:
            msg = f"a walkover between {match.side_1} and {match.side_2} is a draw"
            raise ValueError(msg)
        games = WALKOVER_GAMES[match_format]
        return games if match.outcome is Outcome.SIDE_1 else -games
    return sum(match.games.count(side) * sign for side, sign in _GAME_SIGNS)


_GAME_SIGNS = ((Outcome.SIDE_1, 1), (Outcome.SIDE_2, -1))


def _rank(
    order: Sequence[EntryId],
    tallies: dict[EntryId, _Tally],
    meetings: dict[frozenset[EntryId], Counter[EntryId]],
) -> list[tuple[EntryId, int, RoundRobinTiebreaker | None]]:
    """The entries best first, with their place and what puts each above the next."""
    by_points: dict[int, list[EntryId]] = defaultdict(list)
    for entry_id in order:  # stable: level entries keep the seed order
        by_points[tallies[entry_id].points].append(entry_id)
    ranked: list[tuple[EntryId, int, RoundRobinTiebreaker | None]] = []
    for points in sorted(by_points, reverse=True):
        level = by_points[points]
        for block, ahead_by in _break_tie(level, tallies, meetings):
            place = len(ranked) + 1
            *sharing, last = block
            ranked.extend((entry_id, place, None) for entry_id in sharing)
            ranked.append((last, place, ahead_by))
    return ranked


def _break_tie(
    level: Sequence[EntryId],
    tallies: dict[EntryId, _Tally],
    meetings: dict[frozenset[EntryId], Counter[EntryId]],
) -> list[tuple[list[EntryId], RoundRobinTiebreaker | None]]:
    """Split entries level on points into blocks sharing a place (BR-101).

    Each block comes with the tie-breaker that puts it above the next block of
    the same points, or None for the last one.
    """
    if len(level) == 2:  # noqa: PLR2004  (BR-101 names exactly two)
        first, second = level
        between = meetings.get(frozenset(level), Counter[EntryId]())
        if between[first] != between[second]:
            better, worse = sorted(level, key=lambda e: -between[e])
            return [
                ([better], RoundRobinTiebreaker.HEAD_TO_HEAD),
                ([worse], None),
            ]
    by_difference: dict[tuple[int, int], list[EntryId]] = defaultdict(list)
    for entry_id in level:
        tally = tallies[entry_id]
        key = (tally.game_difference, tally.score_difference)
        by_difference[key].append(entry_id)
    differences = sorted(by_difference, reverse=True)
    return [
        (by_difference[difference], _ahead_by(difference, following))
        for difference, following in zip(
            differences, [*differences[1:], None], strict=True
        )
    ]


def _ahead_by(
    difference: tuple[int, int], following: tuple[int, int] | None
) -> RoundRobinTiebreaker | None:
    """What puts the block with `difference` above the next one, if any (BR-101)."""
    if following is None:
        return None
    if difference[0] != following[0]:
        return RoundRobinTiebreaker.GAME_DIFFERENCE
    return RoundRobinTiebreaker.SCORE_DIFFERENCE


def standing_of(rows: Iterable[StandingRow]) -> tuple[tuple[EntryId, ...], ...]:
    """The rows as tie groups, best first, for `places.place_entries` (BR-103)."""
    groups: dict[int, list[EntryId]] = defaultdict(list)
    for row in rows:
        groups[row.place].append(row.entry_id)
    return tuple(tuple(groups[place]) for place in sorted(groups))
