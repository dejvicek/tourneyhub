from fractions import Fraction
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.ids import EntryId, PlayerId
from tourneyhub.engine.places import (
    EntryPlace,
    KnockoutResult,
    PlacingEntry,
    place_entries,
)
from tourneyhub.engine.season_points import season_points, shared_place_points

DEFAULT_TABLE = [10, 8, 6, 4, 2]  # FR-011


def eid(n: int) -> EntryId:
    return EntryId(UUID(int=n))


def pid(n: int) -> PlayerId:
    return PlayerId(UUID(int=n))


def placed(n: int, place: int, *players: int) -> EntryPlace:
    """Entry `n` at `place` with the given players, or the one player `n`."""
    return EntryPlace(
        entry_id=EntryId(UUID(int=n)),
        player_ids=tuple(PlayerId(UUID(int=p)) for p in players or (n,)),
        place=place,
    )


def by_player(places: list[EntryPlace], table: list[int]) -> dict[int, int]:
    return {row.player_id.int: row.points for row in season_points(places, table)}


# BR-110, BR-111 vectors


def test_br110_each_place_earns_the_points_of_the_table() -> None:
    places = [placed(1, 1), placed(2, 2), placed(3, 3), placed(4, 4), placed(5, 5)]

    points = by_player(places, DEFAULT_TABLE)

    assert points == {1: 10, 2: 8, 3: 6, 4: 4, 5: 2}


def test_br110_places_beyond_the_table_earn_nothing() -> None:
    places = [placed(n, n) for n in range(1, 9)]

    points = by_player(places, DEFAULT_TABLE)

    assert [points[n] for n in (5, 6, 7, 8)] == [2, 0, 0, 0]


def test_br110_an_empty_table_earns_nothing() -> None:
    assert by_player([placed(1, 1), placed(2, 2)], []) == {1: 0, 2: 0}


def test_br111_two_pairs_sharing_third_get_five_each() -> None:
    assert shared_place_points(place=3, entry_count=2, table=DEFAULT_TABLE) == 5


def test_br111_four_entries_sharing_fifth_get_zero_after_rounding_down() -> None:
    assert shared_place_points(place=5, entry_count=4, table=DEFAULT_TABLE) == 0


def test_br111_the_average_is_rounded_down_not_to_nearest() -> None:
    table = [9, 6, 4]

    assert shared_place_points(place=1, entry_count=2, table=table) == 7  # 7.5
    assert shared_place_points(place=2, entry_count=2, table=table) == 5  # 5.0
    assert shared_place_points(place=1, entry_count=3, table=table) == 6  # 6.33


def test_br111_a_shared_block_running_past_the_table_counts_the_missing_places_as_0() -> (
    None
):
    # covers 4th, 5th and 6th: (4 + 2 + 0) / 3 = 2
    assert shared_place_points(place=4, entry_count=3, table=DEFAULT_TABLE) == 2


def test_br111_a_block_wholly_beyond_the_table_gets_zero() -> None:
    assert shared_place_points(place=9, entry_count=2, table=DEFAULT_TABLE) == 0


def test_prd51_a_dyp_night_awards_ten_eight_five_two_and_zero() -> None:
    pairs = [
        PlacingEntry(entry_id=eid(n), player_ids=(pid(n), pid(10 + n)))
        for n in range(1, 7)
    ]
    knockout = [
        KnockoutResult(round_no=1, winner_id=eid(1), loser_id=eid(4)),
        KnockoutResult(round_no=1, winner_id=eid(2), loser_id=eid(3)),
        KnockoutResult(round_no=2, winner_id=eid(1), loser_id=eid(2)),
    ]
    # round robin order of the six pairs; 5 and 6 did not qualify
    group = [(eid(n),) for n in (1, 2, 3, 4, 5, 6)]

    places = place_entries(pairs, standing=group, knockout=knockout)
    points = by_player(list(places), DEFAULT_TABLE)

    assert points == {
        1: 10, 11: 10, 2: 8, 12: 8, 3: 5, 13: 5, 4: 5, 14: 5, 5: 2, 15: 2, 6: 0, 16: 0,
    }  # fmt: skip


def test_prd52_a_monster_dyp_night_gives_players_after_the_pairs_their_own_places() -> (
    None
):
    players = [
        PlacingEntry(entry_id=eid(n), player_ids=(pid(n),)) for n in range(1, 16)
    ]
    pairs = [
        PlacingEntry(entry_id=eid(100 + n), player_ids=(pid(n), pid(n + 4)))
        for n in range(1, 5)
    ]
    knockout = [
        KnockoutResult(round_no=1, winner_id=eid(101), loser_id=eid(104)),
        KnockoutResult(round_no=1, winner_id=eid(102), loser_id=eid(103)),
        KnockoutResult(round_no=2, winner_id=eid(101), loser_id=eid(102)),
    ]

    places = place_entries(
        [*players, *pairs],
        standing=[(eid(n),) for n in range(1, 16)],
        knockout=knockout,
    )
    points = by_player(list(places), DEFAULT_TABLE)

    assert points[1] == points[5] == 10
    assert points[2] == points[6] == 8
    assert points[3] == points[7] == points[4] == points[8] == 5
    assert [points[n] for n in range(9, 16)] == [2, 0, 0, 0, 0, 0, 0]  # 5th to 11th


def test_br100_the_players_of_a_pair_each_get_the_full_points() -> None:
    rows = season_points([placed(1, 1, 11, 12)], DEFAULT_TABLE)

    assert [
        (row.player_id.int, row.entry_id.int, row.place, row.points) for row in rows
    ] == [
        (11, 1, 1, 10),
        (12, 1, 1, 10),
    ]


def test_br110_players_come_out_by_place_and_then_by_id() -> None:
    places = [placed(2, 2, 9), placed(1, 1, 8, 3)]

    rows = season_points(places, DEFAULT_TABLE)

    assert [row.player_id.int for row in rows] == [3, 8, 9]


def test_br110_no_entries_earn_no_points() -> None:
    assert season_points([], DEFAULT_TABLE) == ()


# Refusals (caller bugs)


def test_an_entry_given_twice_is_refused() -> None:
    with pytest.raises(ValueError, match="given twice"):
        season_points([placed(1, 1), placed(1, 2)], DEFAULT_TABLE)


def test_a_player_in_two_entries_is_refused() -> None:
    with pytest.raises(ValueError, match="given twice"):
        season_points([placed(1, 1, 7), placed(2, 2, 7)], DEFAULT_TABLE)


@pytest.mark.parametrize(
    "places",
    [
        pytest.param([placed(1, 2)], id="does-not-start-at-1"),
        pytest.param([placed(1, 1), placed(2, 3)], id="gap"),
        pytest.param(
            [placed(1, 1), placed(2, 1), placed(3, 2)], id="no-skip-after-share"
        ),
        pytest.param([placed(1, 0)], id="zero"),
    ],
)
def test_br104_places_that_numbering_would_not_produce_are_refused(
    places: list[EntryPlace],
) -> None:
    with pytest.raises(ValueError, match="expected"):
        season_points(places, DEFAULT_TABLE)


@pytest.mark.parametrize(
    ("place", "entry_count"),
    [pytest.param(0, 1, id="place-0"), pytest.param(1, 0, id="no-entries")],
)
def test_br111_a_block_needs_a_place_and_an_entry(place: int, entry_count: int) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        shared_place_points(place=place, entry_count=entry_count, table=DEFAULT_TABLE)


# Properties

tables = st.lists(st.integers(min_value=0, max_value=100), max_size=12).map(
    lambda values: sorted(values, reverse=True)
)
"""Whole numbers, none above the place before it (FR-011)."""


@st.composite
def results_of_a_tournament(draw: st.DrawFn) -> list[EntryPlace]:
    """Entries of one or two players in shared place blocks, numbered as BR-104."""
    sizes = draw(
        st.lists(st.integers(min_value=1, max_value=5), min_size=1, max_size=10)
    )
    pairs = draw(st.booleans())
    places: list[EntryPlace] = []
    place = 1
    entry = 0
    for size in sizes:
        for _ in range(size):
            entry += 1
            players = (2 * entry, 2 * entry + 1) if pairs else (2 * entry,)
            places.append(placed(entry, place, *players))
        place += size
    return places


def exact_points(place: int, count: int, table: list[int]) -> int:
    """BR-111 with exact fractions: the average of the covered places, floored."""
    covered = [
        table[p - 1] if p <= len(table) else 0 for p in range(place, place + count)
    ]
    return int(Fraction(sum(covered), count) // 1)


@given(places=results_of_a_tournament(), table=tables)
def test_br111_each_entry_gets_the_floored_average_of_the_places_it_covers(
    places: list[EntryPlace], table: list[int]
) -> None:
    sharing = {p.place: sum(1 for q in places if q.place == p.place) for p in places}

    rows = season_points(places, table)

    for row in rows:
        assert row.points == exact_points(row.place, sharing[row.place], table)


@given(places=results_of_a_tournament(), table=tables)
def test_br100_every_player_of_an_entry_gets_the_same_points(
    places: list[EntryPlace], table: list[int]
) -> None:
    rows = season_points(places, table)

    assert {row.player_id for row in rows} == {p for e in places for p in e.player_ids}
    for entry in places:
        mine = {row.points for row in rows if row.entry_id == entry.entry_id}
        assert len(mine) == 1


@given(places=results_of_a_tournament(), table=tables)
def test_br110_a_better_place_never_earns_fewer_points(
    places: list[EntryPlace], table: list[int]
) -> None:
    rows = season_points(places, table)

    ordered = sorted({(row.place, row.points) for row in rows})
    assert [points for _, points in ordered] == sorted(
        (points for _, points in ordered), reverse=True
    )


@given(places=results_of_a_tournament(), table=tables)
def test_br111_a_block_hands_out_about_what_its_covered_places_are_worth(
    places: list[EntryPlace], table: list[int]
) -> None:
    entry_points = {row.entry_id: row.points for row in season_points(places, table)}

    for place in {entry.place for entry in places}:
        block = [entry for entry in places if entry.place == place]
        points = entry_points[block[0].entry_id]
        covered = sum(
            table[p - 1] if p <= len(table) else 0
            for p in range(place, place + len(block))
        )
        assert len(block) * points <= covered < len(block) * (points + 1)


@given(places=results_of_a_tournament(), table=tables, data=st.data())
def test_br110_the_points_do_not_depend_on_the_order_of_the_entries(
    places: list[EntryPlace], table: list[int], data: st.DataObject
) -> None:
    shuffled = data.draw(st.permutations(places))

    assert season_points(shuffled, table) == season_points(places, table)


@given(places=results_of_a_tournament(), table=tables)
def test_br110_places_beyond_the_table_earn_zero(
    places: list[EntryPlace], table: list[int]
) -> None:
    for row in season_points(places, table):
        if row.place > len(table):
            assert row.points == 0
