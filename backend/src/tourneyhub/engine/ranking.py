"""The league ranking used for seeding and draws (BR-020)."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from tourneyhub.engine.ids import PlayerId, ensure_distinct
from tourneyhub.engine.lots import lot_digest

LEAGUE_RANKING_PURPOSE = "league-ranking"
"""The purpose of the ranking's final lot, keyed on the tournament's seed (ADR-010)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayerRecord:
    """What the league ranking knows about one player (BR-020).

    Attributes:
        player_id: The player.
        season_points: The player's points in the current season.
        tournament_wins: Tournaments the player won in the current season.
        last_season_place: The player's final place in the previous season's
            standings, or `None` without one.
    """

    player_id: PlayerId
    season_points: int
    tournament_wins: int
    last_season_place: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class RankedPlayer:
    """One player's place in the league ranking (BR-020, ADR-009).

    Attributes:
        player_id: The player.
        position: 1 for the best-ranked player; every player has their own.
        is_decided_by_lot: The player ties another on every criterion, so the
            lot decided the order between them.
        tie_group: The position of the best-ranked player this player ties on
            every criterion, the player's own position without a tie. Two
            players' order was decided by lot exactly when they share it.
    """

    player_id: PlayerId
    position: int
    is_decided_by_lot: bool
    tie_group: int


def rank_league(
    players: Iterable[PlayerRecord], *, rng_seed: bytes
) -> tuple[RankedPlayer, ...]:
    """Order the league's players into the league ranking (BR-020, ADR-010).

    The order is: more current season points first, then more tournament wins,
    then the better final place last season, with players without one after
    those with one, and then by lot. The lot uses the tournament's `rng_seed`
    with the purpose `league-ranking`, so tied players are drawn afresh for
    each tournament but the same way on every read.

    Pass every player of the league: seeding (BR-021) adds up positions in
    this ranking.

    Returns:
        The players, best-ranked first, with positions 1 to n.

    Raises:
        ValueError: A player is given twice.
    """
    records = tuple(players)
    ensure_distinct(record.player_id for record in records)

    def criteria(record: PlayerRecord) -> tuple[int, int, bool, int]:
        place = record.last_season_place
        return (
            -record.season_points,
            -record.tournament_wins,
            place is None,
            0 if place is None else place,
        )

    ties = Counter(criteria(record) for record in records)
    ordered = sorted(
        records,
        key=lambda record: (
            criteria(record),
            lot_digest(
                rng_seed=rng_seed,
                purpose=LEAGUE_RANKING_PURPOSE,
                candidate=record.player_id,
            ),
        ),
    )
    tie_groups: dict[tuple[int, int, bool, int], int] = {}
    for position, record in enumerate(ordered, start=1):
        tie_groups.setdefault(criteria(record), position)
    return tuple(
        RankedPlayer(
            player_id=record.player_id,
            position=position,
            is_decided_by_lot=ties[criteria(record)] > 1,
            tie_group=tie_groups[criteria(record)],
        )
        for position, record in enumerate(ordered, start=1)
    )
