from collections import Counter
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.errors import NotEnoughEntriesError
from tourneyhub.engine.ids import EntryId
from tourneyhub.engine.schedule import (
    ScheduledRound,
    check_entry_count,
    minimum_entries,
    round_robin,
    seed_order,
)
from tourneyhub.engine.tournaments import TournamentType


def eid(seed: int) -> EntryId:
    """The entry with this seed; its id is the seed."""
    return EntryId(UUID(int=seed))


def seeds(count: int) -> list[EntryId]:
    return [eid(seed) for seed in range(1, count + 1)]


def pairings(round_: ScheduledRound) -> list[tuple[int, int]]:
    return [(match.side_1.int, match.side_2.int) for match in round_.matches]


# ---------------------------------------------------------------- the minimum


@pytest.mark.parametrize(
    ("tournament_type", "third_place_match", "minimum"),
    [
        pytest.param(TournamentType.SINGLES, False, 2, id="FR-032-two-entries"),
        pytest.param(TournamentType.DOUBLES, True, 4, id="FR-032-third-place"),
        pytest.param(TournamentType.MONSTER_DYP, False, 4, id="FR-032-monster-dyp"),
    ],
)
def test_fr032_the_minimum_number_of_entries(
    tournament_type: TournamentType, third_place_match: bool, minimum: int
) -> None:
    assert (
        minimum_entries(
            tournament_type=tournament_type, third_place_match=third_place_match
        )
        == minimum
    )


def test_fr032_fewer_entries_than_the_minimum_are_refused() -> None:
    with pytest.raises(NotEnoughEntriesError) as raised:
        check_entry_count(
            tournament_type=TournamentType.DYP, third_place_match=False, given=1
        )

    assert (raised.value.minimum, raised.value.given) == (2, 1)


def test_fr032_the_minimum_itself_is_enough() -> None:
    check_entry_count(
        tournament_type=TournamentType.SINGLES, third_place_match=True, given=4
    )


# ---------------------------------------------------------------- the seed order


def test_fr034_entries_come_in_seed_order() -> None:
    order = seed_order([(eid(30), 3), (eid(10), 1), (eid(20), 2)])

    assert order == (eid(10), eid(20), eid(30))


@pytest.mark.parametrize(
    "given_seeds",
    [
        pytest.param([(eid(1), 1), (eid(2), None)], id="no-seed"),
        pytest.param([(eid(1), 1), (eid(2), 1)], id="seed-twice"),
        pytest.param([(eid(1), 1), (eid(2), 3)], id="seed-gap"),
        pytest.param([(eid(1), 1), (eid(1), 2)], id="entry-twice"),
    ],
)
def test_fr034_seeds_that_are_not_one_to_n_are_a_caller_bug(
    given_seeds: list[tuple[EntryId, int | None]],
) -> None:
    with pytest.raises(ValueError, match=r"seed|given twice"):
        seed_order(given_seeds)


# ---------------------------------------------------------------- round robin


def test_br051_round_one_pairs_the_first_seed_with_the_last() -> None:
    rounds = round_robin(seeds(8), legs=1)

    assert pairings(rounds[0]) == [(1, 8), (2, 7), (3, 6), (4, 5)]
    assert pairings(rounds[1]) == [(1, 7), (8, 6), (2, 5), (3, 4)]
    assert rounds[0].sitting_out is None


def test_br051_with_an_odd_number_one_entry_sits_out_each_round() -> None:
    rounds = round_robin(seeds(5), legs=1)

    assert [round_.sitting_out for round_ in rounds] == [
        eid(1),
        eid(4),
        eid(2),
        eid(5),
        eid(3),
    ]
    assert pairings(rounds[0]) == [(2, 5), (3, 4)]


def test_br050_two_entries_play_one_match() -> None:
    rounds = round_robin(seeds(2), legs=1)

    assert [(r.round_no, pairings(r), r.sitting_out) for r in rounds] == [
        (1, [(1, 2)], None)
    ]


def test_br052_the_second_leg_repeats_the_first_with_the_sides_swapped() -> None:
    rounds = round_robin(seeds(3), legs=2)

    assert [r.round_no for r in rounds] == [1, 2, 3, 4, 5, 6]
    assert pairings(rounds[3]) == [(b, a) for a, b in pairings(rounds[0])]
    assert rounds[3].sitting_out == rounds[0].sitting_out


@pytest.mark.parametrize("legs", [0, 3])
def test_br050_a_round_robin_is_played_once_or_twice(legs: int) -> None:
    with pytest.raises(ValueError, match="once or twice"):
        round_robin(seeds(4), legs=legs)


@pytest.mark.parametrize("count", [0, 1])
def test_fr032_fewer_than_two_entries_are_a_caller_bug(count: int) -> None:
    with pytest.raises(ValueError, match="needs 2 entries"):
        round_robin(seeds(count), legs=1)


def test_adr009_an_entry_given_twice_is_a_caller_bug() -> None:
    with pytest.raises(ValueError, match="given twice"):
        round_robin([eid(1), eid(1)], legs=1)


entry_counts = st.integers(min_value=2, max_value=32)
legs_counts = st.sampled_from([1, 2])


@given(entry_counts, legs_counts)
def test_br050_every_two_entries_meet_once_per_leg(count: int, legs: int) -> None:
    rounds = round_robin(seeds(count), legs=legs)

    met = Counter(
        frozenset({match.side_1, match.side_2})
        for round_ in rounds
        for match in round_.matches
    )
    assert len(met) == count * (count - 1) // 2
    assert set(met.values()) == {legs}


@given(entry_counts, legs_counts)
def test_br051_no_entry_plays_twice_in_a_round(count: int, legs: int) -> None:
    rounds = round_robin(seeds(count), legs=legs)

    for round_ in rounds:
        playing = [e for match in round_.matches for e in (match.side_1, match.side_2)]
        present = [*playing, *([round_.sitting_out] if round_.sitting_out else [])]
        assert sorted(present) == seeds(count)
        assert len(round_.matches) == count // 2


@given(entry_counts, legs_counts)
def test_br051_every_entry_sits_out_equally_often(count: int, legs: int) -> None:
    rounds = round_robin(seeds(count), legs=legs)

    sat_out = Counter(r.sitting_out for r in rounds if r.sitting_out is not None)
    if count % 2:
        assert sat_out == dict.fromkeys(seeds(count), legs)
        assert len(rounds) == legs * count
    else:
        assert not sat_out
        assert len(rounds) == legs * (count - 1)


@given(entry_counts)
def test_br052_the_second_leg_repeats_each_round_and_swaps_every_side(
    count: int,
) -> None:
    rounds = round_robin(seeds(count), legs=2)

    half = len(rounds) // 2
    assert [r.round_no for r in rounds] == list(range(1, 2 * half + 1))
    for first, second in zip(rounds[:half], rounds[half:], strict=True):
        assert pairings(second) == [(b, a) for a, b in pairings(first)]
        assert second.sitting_out == first.sitting_out
