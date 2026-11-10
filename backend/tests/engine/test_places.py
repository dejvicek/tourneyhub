from collections.abc import Iterable
from itertools import chain, cycle, pairwise
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


def eid(n: int) -> EntryId:
    return EntryId(UUID(int=n))


def entry(n: int, *players: int) -> PlacingEntry:
    """Entry `n` with the given players, or the one player `n`."""
    return PlacingEntry(
        entry_id=eid(n),
        player_ids=tuple(PlayerId(UUID(int=p)) for p in players or (n,)),
    )


def win(round_no: int, winner: int, loser: int) -> KnockoutResult:
    return KnockoutResult(round_no=round_no, winner_id=eid(winner), loser_id=eid(loser))


def third(winner: int, loser: int) -> KnockoutResult:
    return KnockoutResult(
        round_no=3, winner_id=eid(winner), loser_id=eid(loser), is_third_place=True
    )


def table(places: Iterable[EntryPlace]) -> dict[int, int]:
    """Map each entry number to its place."""
    return {place.entry_id.int: place.place for place in places}


def standing(*groups: tuple[int, ...]) -> list[tuple[EntryId, ...]]:
    return [tuple(eid(n) for n in group) for group in groups]


# Group phase only (BR-101, BR-103)


def test_br103_a_group_phase_alone_places_by_its_standing() -> None:
    entries = [entry(n) for n in range(1, 5)]

    places = place_entries(entries, standing=standing((3,), (1,), (4,), (2,)))

    assert table(places) == {3: 1, 1: 2, 4: 3, 2: 4}


def test_br101_entries_level_after_every_tie_breaker_share_the_place() -> None:
    entries = [entry(n) for n in range(1, 6)]

    places = place_entries(entries, standing=standing((2,), (1, 4), (5,), (3,)))

    assert table(places) == {2: 1, 1: 2, 4: 2, 5: 4, 3: 5}


def test_br100_every_player_of_an_entry_gets_the_entrys_place() -> None:
    entries = [entry(1, 11, 12), entry(2, 21, 22)]

    places = place_entries(entries, standing=standing((2,), (1,)))

    assert [(p.entry_id.int, p.player_ids, p.place) for p in places] == [
        (2, (PlayerId(UUID(int=21)), PlayerId(UUID(int=22))), 1),
        (1, (PlayerId(UUID(int=11)), PlayerId(UUID(int=12))), 2),
    ]


def test_br104_numbering_skips_after_a_shared_place() -> None:
    entries = [entry(n) for n in range(1, 8)]

    places = place_entries(entries, standing=standing((1,), (2,), (3, 4), (5, 6), (7,)))

    assert table(places) == {1: 1, 2: 2, 3: 3, 4: 3, 5: 5, 6: 5, 7: 7}


def test_br100_entries_of_a_place_come_out_by_entry_id() -> None:
    entries = [entry(n) for n in range(1, 4)]

    places = place_entries(entries, standing=standing((3, 1, 2)))

    assert [place.entry_id.int for place in places] == [1, 2, 3]


# The knockout, BR-102


def test_br102_the_final_gives_first_and_second() -> None:
    entries = [entry(1), entry(2)]

    places = place_entries(entries, knockout=[win(1, 2, 1)])

    assert table(places) == {2: 1, 1: 2}


def test_br102_without_a_third_place_match_the_semifinal_losers_share_third() -> None:
    entries = [entry(n) for n in range(1, 5)]
    results = [win(1, 1, 4), win(1, 2, 3), win(2, 2, 1)]

    places = place_entries(entries, knockout=results)

    assert table(places) == {2: 1, 1: 2, 3: 3, 4: 3}


def test_br102_a_third_place_match_gives_third_and_fourth() -> None:
    entries = [entry(n) for n in range(1, 5)]
    results = [win(1, 1, 4), win(1, 2, 3), win(2, 2, 1), third(4, 3)]

    places = place_entries(entries, knockout=results, third_place_match=True)

    assert table(places) == {2: 1, 1: 2, 4: 3, 3: 4}


def test_br102_losers_of_an_earlier_round_share_a_place_block() -> None:
    entries = [entry(n) for n in range(1, 9)]
    results = [
        win(1, 1, 8),
        win(1, 4, 5),
        win(1, 3, 6),
        win(1, 2, 7),
        win(2, 1, 4),
        win(2, 2, 3),
        win(3, 1, 2),
    ]

    places = place_entries(entries, knockout=results)

    # the quarterfinal losers share 5th (BR-102); next would be 9th
    assert table(places) == {1: 1, 2: 2, 4: 3, 3: 3, 8: 5, 5: 5, 6: 5, 7: 5}


def test_br102_round_of_16_losers_share_ninth() -> None:
    entries = [entry(n) for n in range(1, 17)]
    results = [win(1, n, n + 8) for n in range(1, 9)]
    results += [win(2, n, n + 4) for n in range(1, 5)]
    results += [win(3, 1, 3), win(3, 2, 4), win(4, 1, 2)]

    places = place_entries(entries, knockout=results)

    assert {n: p for n, p in table(places).items() if n > 8} == dict.fromkeys(
        range(9, 17), 9
    )
    assert {n: p for n, p in table(places).items() if 5 <= n <= 8} == dict.fromkeys(
        range(5, 9), 5
    )


def test_br102_an_entry_with_a_bye_is_placed_by_the_round_it_loses_in() -> None:
    # 3 entries: 2 and 3 play round 1, 1 has a bye and meets the winner
    entries = [entry(n) for n in range(1, 4)]
    results = [win(1, 2, 3), win(2, 1, 2)]

    places = place_entries(entries, knockout=results)

    assert table(places) == {1: 1, 2: 2, 3: 3}


def test_br102_five_entries_put_the_round_one_loser_fifth() -> None:
    # 8-slot bracket with 3 byes: 4 and 5 play round 1
    entries = [entry(n) for n in range(1, 6)]
    results = [win(1, 4, 5), win(2, 1, 4), win(2, 2, 3), win(3, 1, 2)]

    places = place_entries(entries, knockout=results)

    assert table(places) == {1: 1, 2: 2, 4: 3, 3: 3, 5: 5}


def test_br102_a_third_place_match_leaves_earlier_rounds_unchanged() -> None:
    entries = [entry(n) for n in range(1, 9)]
    results = [
        win(1, 1, 8),
        win(1, 4, 5),
        win(1, 3, 6),
        win(1, 2, 7),
        win(2, 1, 4),
        win(2, 2, 3),
        win(3, 1, 2),
        third(3, 4),
    ]

    places = place_entries(entries, knockout=results, third_place_match=True)

    assert table(places) == {1: 1, 2: 2, 3: 3, 4: 4, 8: 5, 5: 5, 6: 5, 7: 5}


# Group phase and knockout (BR-103)


def test_br103_non_qualifiers_follow_the_knockout_in_group_order() -> None:
    group = [entry(n) for n in range(1, 7)]
    knockout_entries = [entry(10 + n, n) for n in (1, 2, 3, 4)]  # own ids, same players
    results = [win(1, 11, 14), win(1, 12, 13), win(2, 11, 12)]

    places = place_entries(
        [*group, *knockout_entries],
        standing=standing((1,), (2,), (3,), (4,), (5,), (6,)),
        knockout=results,
    )

    assert table(places) == {11: 1, 12: 2, 13: 3, 14: 3, 5: 5, 6: 6}


def test_br103_after_eight_knockout_pairs_the_best_non_qualifier_is_ninth() -> None:
    group = [entry(n, n, 100 + n) for n in range(1, 11)]  # ten pairs
    knockout_entries = [entry(20 + n, n, 100 + n) for n in range(1, 9)]
    results = [
        win(1, 21, 28),
        win(1, 24, 25),
        win(1, 23, 26),
        win(1, 22, 27),
        win(2, 21, 24),
        win(2, 22, 23),
        win(3, 21, 22),
    ]

    places = place_entries(
        [*group, *knockout_entries],
        standing=standing(*((n,) for n in range(1, 11))),
        knockout=results,
    )

    assert table(places)[9] == 9
    assert table(places)[10] == 10


def test_br103_non_qualifiers_level_in_the_group_phase_still_share() -> None:
    group = [entry(n) for n in range(1, 7)]
    knockout_entries = [entry(10 + n, n) for n in (1, 2)]
    results = [win(1, 11, 12)]

    places = place_entries(
        [*group, *knockout_entries],
        standing=standing((1,), (2,), (3, 4), (5,), (6,)),
        knockout=results,
    )

    assert table(places) == {11: 1, 12: 2, 3: 3, 4: 3, 5: 5, 6: 6}


def test_br103_a_tie_group_cut_by_the_knockout_leaves_the_rest_together() -> None:
    group = [entry(n) for n in range(1, 6)]
    knockout_entries = [entry(10 + n, n) for n in (1, 2, 3)]  # 3 of the tie (3, 4)
    results = [win(1, 12, 13), win(2, 11, 12)]  # entry 11 had a bye

    places = place_entries(
        [*group, *knockout_entries],
        standing=standing((1,), (2,), (3, 4), (5,)),
        knockout=results,
    )

    # entry 4 stays behind alone from the tie (3, 4), and 5 follows it
    assert table(places) == {11: 1, 12: 2, 13: 3, 4: 4, 5: 5}


def test_prd52_monster_dyp_pairs_in_the_knockout_players_follow_one_by_one() -> None:
    players = [entry(n) for n in range(1, 16)]  # 15 players, in group order
    pairs = [
        entry(101, 1, 5),
        entry(102, 2, 6),
        entry(103, 3, 7),
        entry(104, 4, 8),
    ]
    results = [win(1, 101, 104), win(1, 102, 103), win(2, 101, 102)]

    places = place_entries(
        [*players, *pairs],
        standing=standing(*((n,) for n in range(1, 16))),
        knockout=results,
    )

    expected = {101: 1, 102: 2, 103: 3, 104: 3}
    expected |= {n: n - 4 for n in range(9, 16)}  # 9th player is 5th, ... 15th is 11th
    assert table(places) == expected


# Refusals (caller bugs)


def test_a_tournament_with_no_results_has_nothing_to_place() -> None:
    with pytest.raises(ValueError, match="nothing to place"):
        place_entries([entry(1), entry(2)])


def test_an_entry_given_twice_is_refused() -> None:
    with pytest.raises(ValueError, match="given twice"):
        place_entries([entry(1), entry(1)], standing=standing((1,)))


def test_an_unknown_entry_in_the_standing_is_refused() -> None:
    with pytest.raises(ValueError, match="not among the entries"):
        place_entries([entry(1)], standing=standing((1,), (2,)))


def test_an_entry_in_the_standing_twice_is_refused() -> None:
    with pytest.raises(ValueError, match="given twice"):
        place_entries([entry(1), entry(2)], standing=standing((1,), (2, 1)))


def test_a_knockout_of_only_a_third_place_match_is_refused() -> None:
    with pytest.raises(ValueError, match="needs a final"):
        place_entries(
            [entry(1), entry(2)], knockout=[third(1, 2)], third_place_match=True
        )


def test_a_last_round_with_two_matches_is_refused() -> None:
    entries = [entry(n) for n in range(1, 5)]

    with pytest.raises(ValueError, match="not one final"):
        place_entries(entries, knockout=[win(1, 1, 2), win(1, 3, 4)])


def test_two_third_place_matches_are_refused() -> None:
    entries = [entry(n) for n in range(1, 5)]
    results = [win(1, 1, 4), win(1, 2, 3), win(2, 2, 1), third(4, 3), third(3, 4)]

    with pytest.raises(ValueError, match="third-place matches"):
        place_entries(entries, knockout=results, third_place_match=True)


def test_an_entry_that_loses_twice_is_refused() -> None:
    entries = [entry(n) for n in range(1, 4)]

    with pytest.raises(ValueError, match="given twice"):
        place_entries(entries, knockout=[win(1, 2, 3), win(2, 1, 3)])


def test_a_final_winner_who_lost_earlier_is_refused() -> None:
    entries = [entry(n) for n in range(1, 4)]

    with pytest.raises(ValueError, match="given twice"):
        place_entries(entries, knockout=[win(1, 2, 1), win(2, 1, 2)])


def test_a_third_place_match_between_other_entries_is_refused() -> None:
    entries = [entry(n) for n in range(1, 5)]
    results = [win(1, 1, 4), win(1, 2, 3), win(2, 2, 1), third(4, 1)]

    with pytest.raises(ValueError, match="semifinal losers"):
        place_entries(entries, knockout=results, third_place_match=True)


def test_a_third_place_match_without_semifinals_is_refused() -> None:
    entries = [entry(n) for n in range(1, 5)]

    with pytest.raises(ValueError, match="semifinal losers"):
        place_entries(
            entries, knockout=[win(2, 2, 1), third(4, 3)], third_place_match=True
        )


def test_an_entry_missing_from_the_knockout_is_refused() -> None:
    entries = [entry(n) for n in range(1, 5)]
    results = [win(1, 1, 4), win(2, 1, 2)]  # the match of 2 against 3 is missing

    with pytest.raises(ValueError, match="without a place"):
        place_entries(entries, knockout=results)


def test_an_entry_missing_from_the_standing_is_refused() -> None:
    entries = [entry(n) for n in range(1, 4)]

    with pytest.raises(ValueError, match="without a place"):
        place_entries(entries, standing=standing((1,), (2,)))


def test_a_group_entry_only_partly_in_the_knockout_is_refused() -> None:
    entries = [entry(1, 11, 12), entry(21, 11, 99), entry(22, 31, 32)]

    with pytest.raises(ValueError, match="without a place"):
        place_entries(entries, standing=standing((1,)), knockout=[win(1, 21, 22)])


def test_fr037_a_third_place_match_without_a_result_is_refused() -> None:
    entries = [entry(n) for n in range(1, 5)]
    results = [win(1, 1, 4), win(1, 2, 3), win(2, 2, 1)]

    with pytest.raises(ValueError, match="no result"):
        place_entries(entries, knockout=results, third_place_match=True)


def test_fr037_a_third_place_result_without_the_flag_is_refused() -> None:
    entries = [entry(n) for n in range(1, 5)]
    results = [win(1, 1, 4), win(1, 2, 3), win(2, 2, 1), third(4, 3)]

    with pytest.raises(ValueError, match="without that match"):
        place_entries(entries, knockout=results)


# Properties


def play_bracket(
    seeds: list[int], flips: Iterable[bool], *, third_place: bool = False
) -> list[KnockoutResult]:
    """Results of a finished knockout of `seeds`, best seed first.

    Round 1 has the matches that reduce the field to a power of two, and the
    best seeds have byes. A match goes to its first side, or to its second
    when the next value of `flips` is true; once `flips` runs out, to the first.
    """
    flip = chain(flips, cycle([False]))
    rounds = (len(seeds) - 1).bit_length()
    field = list(seeds)
    results: list[KnockoutResult] = []
    for round_no in range(1, rounds + 1):
        matches = (
            len(field) - 2 ** (rounds - round_no) if round_no == 1 else len(field) // 2
        )
        advancing = field[: len(field) - 2 * matches]
        playing = field[len(field) - 2 * matches :]
        losers = []
        for first, second in zip(playing[::2], playing[1::2], strict=True):
            winner, loser = (second, first) if next(flip) else (first, second)
            results.append(win(round_no, winner, loser))
            advancing.append(winner)
            losers.append(loser)
        field = advancing
        if third_place and round_no == rounds - 1:
            first, second = losers
            winner, loser = (second, first) if next(flip) else (first, second)
            results.append(third(winner, loser))
    return results


@st.composite
def brackets(draw: st.DrawFn) -> tuple[int, list[KnockoutResult], bool]:
    """A finished knockout of 2 to 40 entries, with byes and random winners."""
    size = draw(st.integers(min_value=2, max_value=40))
    third_place = size >= 4 and draw(st.booleans())
    flips = draw(st.lists(st.booleans(), min_size=size, max_size=size))
    return (
        size,
        play_bracket(list(range(1, size + 1)), flips, third_place=third_place),
        third_place,
    )


@given(bracket=brackets())
def test_br102_each_round_loses_to_the_place_after_the_entries_still_in(
    bracket: tuple[int, list[KnockoutResult], bool],
) -> None:
    size, results, has_third_place = bracket
    rounds = (size - 1).bit_length()

    places = table(
        place_entries(
            [entry(n) for n in range(1, size + 1)],
            knockout=results,
            third_place_match=has_third_place,
        )
    )

    final = next(r for r in results if r.round_no == rounds and not r.is_third_place)
    assert places[final.winner_id.int] == 1
    assert places[final.loser_id.int] == 2
    for result in results:
        if result.is_third_place:
            assert places[result.winner_id.int] == 3
            assert places[result.loser_id.int] == 4
        elif result.round_no < rounds:
            if has_third_place and result.round_no == rounds - 1:
                continue
            # 2 ** (rounds - r) entries are still in after round r
            assert places[result.loser_id.int] == 2 ** (rounds - result.round_no) + 1


@given(bracket=brackets())
def test_br104_a_knockout_places_every_entry_with_numbering_that_skips(
    bracket: tuple[int, list[KnockoutResult], bool],
) -> None:
    size, results, has_third_place = bracket

    placed = place_entries(
        [entry(n) for n in range(1, size + 1)],
        knockout=results,
        third_place_match=has_third_place,
    )

    assert sorted(place.entry_id.int for place in placed) == list(range(1, size + 1))
    assert [place.place for place in placed] == sorted(place.place for place in placed)
    expected = 1
    for place in sorted({place.place for place in placed}):
        assert place == expected
        expected += sum(1 for other in placed if other.place == place)


@given(bracket=brackets(), data=st.data())
def test_br102_the_places_do_not_depend_on_the_order_of_the_results(
    bracket: tuple[int, list[KnockoutResult], bool], data: st.DataObject
) -> None:
    size, results, has_third_place = bracket
    entries = [entry(n) for n in range(1, size + 1)]

    shuffled = data.draw(st.permutations(results))

    assert place_entries(
        entries, knockout=shuffled, third_place_match=has_third_place
    ) == place_entries(entries, knockout=results, third_place_match=has_third_place)


@st.composite
def standings(draw: st.DrawFn) -> tuple[int, list[tuple[int, ...]], int]:
    """A standing of 2 to 30 entries in tie groups, and a cut of qualifiers."""
    size = draw(st.integers(min_value=2, max_value=30))
    order = draw(st.permutations(range(1, size + 1)))
    cuts = draw(st.sets(st.integers(min_value=1, max_value=size - 1)))
    bounds = [0, *sorted(cuts), size]
    groups = [tuple(order[a:b]) for a, b in pairwise(bounds)]
    qualifiers = draw(st.integers(min_value=2, max_value=size))
    return size, groups, qualifiers


@given(case=standings())
def test_br101_a_standing_alone_places_in_contiguous_blocks_from_first(
    case: tuple[int, list[tuple[int, ...]], int],
) -> None:
    size, groups, _ = case

    places = table(
        place_entries(
            [entry(n) for n in range(1, size + 1)], standing=standing(*groups)
        )
    )

    assert sorted(places) == list(range(1, size + 1))
    for group in groups:
        assert len({places[n] for n in group}) == 1  # level entries share a place
    block_places = sorted(set(places.values()))
    assert block_places[0] == 1
    for place in block_places:
        # a block's place is 1 plus the number of entries ahead of it
        assert place == 1 + sum(1 for other in places.values() if other < place)


@given(case=standings(), data=st.data())
def test_br101_the_places_do_not_depend_on_any_input_order(
    case: tuple[int, list[tuple[int, ...]], int], data: st.DataObject
) -> None:
    size, groups, _ = case
    entries = [entry(n) for n in range(1, size + 1)]
    reordered = [tuple(data.draw(st.permutations(group))) for group in groups]

    assert place_entries(
        data.draw(st.permutations(entries)), standing=standing(*reordered)
    ) == place_entries(entries, standing=standing(*groups))


@given(
    players=st.integers(min_value=8, max_value=24),
    pair_count=st.integers(min_value=2, max_value=4),
    flips=st.lists(st.booleans(), max_size=4),
)
def test_prd52_a_monster_dyp_night_places_every_player_exactly_once(
    players: int, pair_count: int, flips: list[bool]
) -> None:
    singles = [entry(n) for n in range(1, players + 1)]
    # the best 2 * pair_count players form pairs: best with worst, and so on
    pairs = [entry(1000 + i, i + 1, 2 * pair_count - i) for i in range(pair_count)]
    results = play_bracket([1000 + i for i in range(pair_count)], flips)

    placed = place_entries(
        [*singles, *pairs],
        standing=standing(*((n,) for n in range(1, players + 1))),
        knockout=results,
    )

    given_places = sorted(player.int for place in placed for player in place.player_ids)
    assert given_places == list(range(1, players + 1))


@given(case=standings())
def test_br103_non_qualifiers_are_numbered_after_the_knockout_entries(
    case: tuple[int, list[tuple[int, ...]], int],
) -> None:
    size, groups, qualifiers = case
    order = [n for group in groups for n in group]
    qualified = order[:qualifiers]
    group_entries = [entry(n) for n in range(1, size + 1)]
    knockout_entries = [entry(1000 + n, n) for n in qualified]
    # a bracket in which the better group position always wins, seeds as in the order
    results = play_bracket([1000 + n for n in qualified], [])

    places = table(
        place_entries(
            [*group_entries, *knockout_entries],
            standing=standing(*groups),
            knockout=results,
        )
    )

    assert sorted(places) == sorted(
        {1000 + n for n in qualified} | set(order[qualifiers:])
    )
    position = qualifiers + 1
    for group in groups:
        rest = [n for n in group if n not in qualified]
        for n in rest:
            assert places[n] == position
        position += len(rest)
