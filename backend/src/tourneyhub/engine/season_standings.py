"""Season standings and what one tournament changes in them (BR-112, BR-113)."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from tourneyhub.engine.ids import PlayerId, ensure_distinct
from tourneyhub.engine.season_points import PlayerPoints

FIRST_PLACE = 1
"""The place that wins a tournament; entries sharing it all won (BR-104)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SeasonStandingRow:
    """One player's line in the season standings (FR-061, BR-113).

    Attributes:
        place: 1 for the best. Players level on points and wins share the
            place, and the next place skips as many as they are (BR-113,
            BR-104).
        player_id: The player.
        points: The placement points of all the finished tournaments summed
            (BR-112).
        tournaments_played: Finished tournaments the player played in.
        tournament_wins: Finished tournaments in which the player's entry
            was 1st, a shared 1st included.
    """

    place: int
    player_id: PlayerId
    points: int
    tournaments_played: int
    tournament_wins: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SeasonEffectRow:
    """One player's change in the season standings after a tournament.

    Attributes:
        player_id: The player.
        place: The player's place in the season standings with the tournament.
        points: The player's season points with the tournament.
        earned: The placement points the player earned in the tournament; 0
            for a player who did not play in it.
        previous_place: The player's place in the standings of the season's
            other finished tournaments, or `None` for a player who played in
            none of them.
    """

    player_id: PlayerId
    place: int
    points: int
    earned: int
    previous_place: int | None


def season_standings(
    tournaments: Iterable[Iterable[PlayerPoints]],
) -> tuple[SeasonStandingRow, ...]:
    """Rank the players of a season's finished tournaments (FR-061, BR-112, BR-113).

    Pass one `season_points` result per finished tournament; an unfinished
    tournament does not count (BR-112), so it is never passed. Every player
    who played in one appears, one with no points too. Players are ranked by
    total points, then by tournament wins; players still level share the
    place (BR-113), and rows within a place come by player id so that the
    order is the same on every read (ADR-009).

    Returns:
        The players, best first.

    Raises:
        ValueError: A caller bug: a player is in one tournament twice.
    """
    points: defaultdict[PlayerId, int] = defaultdict(int)
    played: defaultdict[PlayerId, int] = defaultdict(int)
    wins: defaultdict[PlayerId, int] = defaultdict(int)
    for tournament in tournaments:
        rows = tuple(tournament)
        ensure_distinct(row.player_id for row in rows)
        for row in rows:
            points[row.player_id] += row.points
            played[row.player_id] += 1
            wins[row.player_id] += row.place == FIRST_PLACE
    ordered = sorted(
        points, key=lambda player: (-points[player], -wins[player], player.int)
    )
    standings: list[SeasonStandingRow] = []
    for position, player in enumerate(ordered, start=1):
        level = standings and (
            (standings[-1].points, standings[-1].tournament_wins)
            == (points[player], wins[player])
        )
        standings.append(
            SeasonStandingRow(
                place=standings[-1].place if level else position,
                player_id=player,
                points=points[player],
                tournaments_played=played[player],
                tournament_wins=wins[player],
            )
        )
    return tuple(standings)


def season_effect(
    tournament: Iterable[PlayerPoints],
    others: Iterable[Iterable[PlayerPoints]],
) -> tuple[SeasonEffectRow, ...]:
    """What a finished tournament changes in the season standings (BR-112).

    `tournament` is the points of the tournament and `others` those of the
    season's other finished tournaments. The standings with the tournament
    are compared with the standings without it, so the answer does not depend
    on the dates: a correction to any result moves the effect with it
    (BR-112).

    Returns:
        A row for every player in the standings with the tournament, in
        standings order, including those who did not play in it.

    Raises:
        ValueError: A caller bug: a player is in one tournament twice.
    """
    played = tuple(tournament)
    others = tuple(tuple(rows) for rows in others)
    before = {row.player_id: row.place for row in season_standings(others)}
    earned = {row.player_id: row.points for row in played}
    return tuple(
        SeasonEffectRow(
            player_id=row.player_id,
            place=row.place,
            points=row.points,
            earned=earned.get(row.player_id, 0),
            previous_place=before.get(row.player_id),
        )
        for row in season_standings((played, *others))
    )
