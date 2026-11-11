from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.ids import EntryId, PlayerId
from tourneyhub.engine.places import EntryPlace
from tourneyhub.engine.season_points import PlayerPoints, season_points
from tourneyhub.engine.season_standings import (
    SeasonStandingRow,
    season_effect,
    season_standings,
)

DEFAULT_TABLE = [10, 8, 6, 4, 2]  # FR-011


def pid(n: int) -> PlayerId:
    return PlayerId(UUID(int=n))


def tournament(*players: int, table: list[int] = DEFAULT_TABLE) -> list[PlayerPoints]:
    """A tournament in which the players finish 1st, 2nd, ... in the given order."""
    places = [
        EntryPlace(
            entry_id=EntryId(UUID(int=player)), player_ids=(pid(player),), place=place
        )
        for place, player in enumerate(players, start=1)
    ]
    return list(season_points(places, table))


def standing(rows: tuple[SeasonStandingRow, ...]) -> list[tuple[int, ...]]:
    """(place, player, points, played, wins) of each row."""
    return [
        (r.place, r.player_id.int, r.points, r.tournaments_played, r.tournament_wins)
        for r in rows
    ]


# FR-061, BR-112, BR-113 vectors


def test_br112_the_points_of_the_finished_tournaments_add_up() -> None:
    first = tournament(1, 2, 3)  # 1: 10, 2: 8, 3: 6
    second = tournament(2, 1, 3)  # 2: 10, 1: 8, 3: 6

    rows = season_standings([first, second])

    # 1 and 2 are level on 18 points and one win each: they share 1st.
    assert standing(rows) == [(1, 1, 18, 2, 1), (1, 2, 18, 2, 1), (3, 3, 12, 2, 0)]


def test_fr061_a_player_with_no_points_still_appears() -> None:
    rows = season_standings([tournament(1, 2, 3, 4, 5, 6)])

    assert standing(rows)[-1] == (6, 6, 0, 1, 0)


def test_br113_wins_rank_players_level_on_points() -> None:
    first = tournament(1, 2, 3)  # 1: 10 (win), 2: 8, 3: 6
    second = tournament(3, 4, 2, 1)  # 3: 10 (win), 4: 8, 2: 6, 1: 4

    rows = season_standings([first, second])

    # 1 and 2 have 14 each; 1 has won a tournament and 2 has not.
    assert standing(rows) == [
        (1, 3, 16, 2, 1),
        (2, 1, 14, 2, 1),
        (3, 2, 14, 2, 0),
        (4, 4, 8, 1, 0),
    ]


def test_br104_a_shared_place_is_followed_by_the_one_that_skips() -> None:
    rows = season_standings([tournament(1, 2, 3, 4), tournament(2, 1, 4, 3)])

    assert [r.place for r in rows] == [1, 1, 3, 3]


def test_br111_a_shared_first_place_is_a_win_for_each_entry() -> None:
    places = [
        EntryPlace(entry_id=EntryId(UUID(int=n)), player_ids=(pid(n),), place=1)
        for n in (1, 2)
    ]

    rows = season_standings([season_points(places, DEFAULT_TABLE)])

    # They cover 1st and 2nd: (10 + 8) / 2 = 9 each.
    assert standing(rows) == [(1, 1, 9, 1, 1), (1, 2, 9, 1, 1)]


def test_br100_both_players_of_a_pair_get_the_entrys_points() -> None:
    places = [
        EntryPlace(entry_id=EntryId(UUID(int=1)), player_ids=(pid(1), pid(2)), place=1)
    ]

    rows = season_standings([season_points(places, DEFAULT_TABLE)])

    assert standing(rows) == [(1, 1, 10, 1, 1), (1, 2, 10, 1, 1)]


def test_br112_a_season_without_finished_tournaments_has_no_standings() -> None:
    assert season_standings([]) == ()


def test_a_player_in_one_tournament_twice_is_refused() -> None:
    twice = tournament(1, 2) + tournament(1, 2)

    with pytest.raises(ValueError, match="given twice"):
        season_standings([twice])


# The effect of one tournament


def test_br112_the_effect_compares_the_standings_with_and_without_it() -> None:
    earlier = tournament(1, 2, 3)  # 1: 10, 2: 8, 3: 6
    this = tournament(3, 2, 4)  # 3: 10, 2: 8, 4: 6

    rows = season_effect(this, [earlier])

    assert [
        (r.player_id.int, r.place, r.points, r.earned, r.previous_place) for r in rows
    ] == [
        (3, 1, 16, 10, 3),
        (2, 2, 16, 8, 2),
        (1, 3, 10, 0, 1),
        (4, 4, 6, 6, None),
    ]


def test_br112_the_only_tournament_of_a_season_has_no_previous_places() -> None:
    rows = season_effect(tournament(1, 2), [])

    assert [(r.player_id.int, r.earned, r.previous_place) for r in rows] == [
        (1, 10, None),
        (2, 8, None),
    ]


# Properties


@st.composite
def seasons(draw: st.DrawFn) -> list[list[PlayerPoints]]:
    """Finished tournaments of up to 8 players in shared place blocks (BR-104)."""
    table = sorted(
        draw(st.lists(st.integers(min_value=0, max_value=100), max_size=8)),
        reverse=True,
    )
    result: list[list[PlayerPoints]] = []
    for _ in range(draw(st.integers(min_value=0, max_value=6))):
        players = draw(
            st.lists(st.integers(min_value=0, max_value=7), min_size=1, unique=True)
        )
        sizes = draw(st.lists(st.integers(min_value=1, max_value=4), min_size=1))
        places: list[EntryPlace] = []
        place = 1
        left = list(players)
        for size in sizes:
            block, left = left[:size], left[size:]
            places += [
                EntryPlace(
                    entry_id=EntryId(UUID(int=p)), player_ids=(pid(p),), place=place
                )
                for p in block
            ]
            place += len(block)
        # Players the blocks left over share the last place after them.
        places += [
            EntryPlace(entry_id=EntryId(UUID(int=p)), player_ids=(pid(p),), place=place)
            for p in left
        ]
        result.append(list(season_points(places, table)))
    return result


@given(season=seasons())
def test_br112_the_season_total_is_the_sum_of_the_tournaments_points(
    season: list[list[PlayerPoints]],
) -> None:
    rows = season_standings(season)

    for r in rows:
        mine = [p for t in season for p in t if p.player_id == r.player_id]
        assert r.points == sum(p.points for p in mine)
        assert r.tournaments_played == len(mine)
        assert r.tournament_wins == sum(p.place == 1 for p in mine)
    assert sum(r.points for r in rows) == sum(p.points for t in season for p in t)
    assert {r.player_id for r in rows} == {p.player_id for t in season for p in t}


@given(season=seasons())
def test_br113_places_follow_points_then_wins_and_share_when_level(
    season: list[list[PlayerPoints]],
) -> None:
    rows = season_standings(season)

    keys = [(-r.points, -r.tournament_wins) for r in rows]
    assert keys == sorted(keys)
    for r, key in zip(rows, keys, strict=True):
        assert r.place == 1 + sum(other < key for other in keys)


@given(season=seasons())
def test_br112_the_effect_adds_the_tournament_to_the_others(
    season: list[list[PlayerPoints]],
) -> None:
    if not season:
        return
    *others, this = season

    effect = season_effect(this, others)

    assert [e.player_id for e in effect] == [
        r.player_id for r in season_standings(season)
    ]
    before = {r.player_id: r for r in season_standings(others)}
    for e in effect:
        previous = before.get(e.player_id)
        assert e.previous_place == (None if previous is None else previous.place)
        assert e.points == (0 if previous is None else previous.points) + e.earned
