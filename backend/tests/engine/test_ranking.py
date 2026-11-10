from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.ranking import PlayerRecord, RankedPlayer, rank_league

SEED = bytes(range(16))


def player(
    n: int, *, points: int = 0, wins: int = 0, place: int | None = None
) -> PlayerRecord:
    return PlayerRecord(
        player_id=PlayerId(UUID(int=n)),
        season_points=points,
        tournament_wins=wins,
        last_season_place=place,
    )


def order(ranking: tuple[RankedPlayer, ...]) -> list[int]:
    return [ranked.player_id.int for ranked in ranking]


def test_br020_ranks_by_season_points_first() -> None:
    players = [player(1, points=5, wins=3), player(2, points=12), player(3, points=8)]

    ranking = rank_league(players, rng_seed=SEED)

    assert order(ranking) == [2, 3, 1]
    assert [ranked.position for ranked in ranking] == [1, 2, 3]
    assert not any(ranked.is_decided_by_lot for ranked in ranking)


def test_br020_breaks_equal_points_by_tournament_wins() -> None:
    players = [player(1, points=10, wins=1, place=1), player(2, points=10, wins=2)]

    ranking = rank_league(players, rng_seed=SEED)

    assert order(ranking) == [2, 1]


def test_br020_breaks_equal_wins_by_last_season_place() -> None:
    players = [
        player(1, points=10, wins=1, place=4),
        player(2, points=10, wins=1, place=2),
    ]

    ranking = rank_league(players, rng_seed=SEED)

    assert order(ranking) == [2, 1]


def test_br020_puts_players_without_a_last_season_place_after_those_with_one() -> None:
    players = [player(1, place=None), player(2, place=30), player(3, place=None)]

    ranking = rank_league(players, rng_seed=SEED)

    assert order(ranking)[0] == 2
    assert [ranked.is_decided_by_lot for ranked in ranking] == [False, True, True]


def test_br020_breaks_a_full_tie_by_the_league_ranking_lot() -> None:
    players = [player(n, points=6, wins=1, place=3) for n in range(1, 6)]
    drawn = order_by_lot(
        (record.player_id for record in players),
        rng_seed=SEED,
        purpose="league-ranking",
    )

    ranking = rank_league(players, rng_seed=SEED)

    assert tuple(ranked.player_id for ranked in ranking) == drawn
    assert all(ranked.is_decided_by_lot for ranked in ranking)


def test_br020_marks_only_the_tied_players_as_decided_by_lot() -> None:
    players = [player(1, points=9), player(2, points=4), player(3, points=4)]

    ranking = rank_league(players, rng_seed=SEED)

    assert order(ranking)[0] == 1
    assert [ranked.is_decided_by_lot for ranked in ranking] == [False, True, True]


def test_br020_tied_players_share_the_position_of_their_best_one() -> None:
    players = [player(1, points=9), player(2, points=4), player(3, points=4)]
    players.append(player(4, points=1))

    ranking = rank_league(players, rng_seed=SEED)

    assert [ranked.tie_group for ranked in ranking] == [1, 2, 2, 4]


def test_br020_refuses_a_player_given_twice() -> None:
    with pytest.raises(ValueError, match="twice"):
        rank_league([player(1), player(1, points=3)], rng_seed=SEED)


records = st.builds(
    PlayerRecord,
    player_id=st.uuids().map(PlayerId),
    season_points=st.integers(min_value=0, max_value=5),
    tournament_wins=st.integers(min_value=0, max_value=2),
    last_season_place=st.none() | st.integers(min_value=1, max_value=4),
)
leagues = st.lists(records, max_size=40, unique_by=lambda record: record.player_id)
seeds = st.binary(min_size=16, max_size=16)


@given(players=leagues, rng_seed=seeds, data=st.data())
def test_br020_ranking_ignores_the_input_order(
    players: list[PlayerRecord], rng_seed: bytes, data: st.DataObject
) -> None:
    reordered = data.draw(st.permutations(players))

    assert rank_league(players, rng_seed=rng_seed) == rank_league(
        reordered, rng_seed=rng_seed
    )


@given(players=leagues, rng_seed=seeds)
def test_br020_ranking_orders_every_player_by_the_criteria(
    players: list[PlayerRecord], rng_seed: bytes
) -> None:
    by_id = {record.player_id: record for record in players}

    ranking = rank_league(players, rng_seed=rng_seed)

    assert [ranked.position for ranked in ranking] == list(range(1, len(players) + 1))
    assert sorted(ranked.player_id for ranked in ranking) == sorted(by_id)
    keys = [
        (
            -by_id[ranked.player_id].season_points,
            -by_id[ranked.player_id].tournament_wins,
            by_id[ranked.player_id].last_season_place or 99,
        )
        for ranked in ranking
    ]
    assert keys == sorted(keys)
