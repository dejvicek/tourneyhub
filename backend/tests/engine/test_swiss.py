from collections import Counter
from collections.abc import Iterable, Sequence
from itertools import combinations
from time import perf_counter
from uuid import UUID

import networkx as nx
import pytest
from hypothesis import assume, example, given, settings
from hypothesis import strategies as st

from tourneyhub.engine.errors import NotEnoughEntriesError
from tourneyhub.engine.ids import EntryId
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.results import tiebreak_purpose
from tourneyhub.engine.swiss import (
    PairingMethod,
    SwissDraw,
    SwissMatch,
    SwissRound,
    SwissStanding,
    draw_first_swiss_round,
    draw_next_swiss_round,
    recommended_minimum_rounds,
    swiss_standings,
)
from tourneyhub.engine.tournaments import DEFAULT_TIEBREAKERS, MatchOutcome, Tiebreaker

SEED = bytes(range(16))

WIN = MatchOutcome.SIDE_1
LOSS = MatchOutcome.SIDE_2
DRAW = MatchOutcome.DRAW


def eid(n: int) -> EntryId:
    return EntryId(UUID(int=n))


def ids(*numbers: int) -> list[EntryId]:
    return [eid(n) for n in numbers]


def match(
    side_1: int,
    side_2: int,
    outcome: MatchOutcome | None = DRAW,
    score_difference: int = 0,
) -> SwissMatch:
    return SwissMatch(
        side_1=eid(side_1),
        side_2=eid(side_2),
        outcome=outcome,
        score_difference=score_difference,
    )


def round_(
    round_no: int, *matches: SwissMatch, sat_out: int | None = None
) -> SwissRound:
    return SwissRound(
        round_no=round_no,
        matches=matches,
        sat_out=() if sat_out is None else (eid(sat_out),),
    )


def met(*pairs: tuple[int, int]) -> list[SwissRound]:
    """One drawn round per pair: enough history to say who has met whom."""
    return [round_(number, match(*pair)) for number, pair in enumerate(pairs, 1)]


def line(
    n: int, position: int, *, points: int = 0, sat_out: int = 0, place: int = 0
) -> SwissStanding:
    """Entry `n` at `position`, sharing `place` when one is given."""
    return SwissStanding(
        entry_id=eid(n),
        position=position,
        place=place or position,
        points=points,
        bh1=0,
        bh2=0,
        score_difference=0,
        played=0,
        won=0,
        drawn=0,
        lost=0,
        sat_out=sat_out,
        is_decided_by_lot=bool(place),
    )


def table(*numbers: int) -> list[SwissStanding]:
    """Entries in this order, each in a place of its own."""
    return [line(n, position) for position, n in enumerate(numbers, 1)]


def standings(
    entries: Iterable[EntryId],
    rounds: Iterable[SwissRound],
    *,
    tiebreakers: Sequence[Tiebreaker] = DEFAULT_TIEBREAKERS,
    sit_out_points: int = 0,
) -> dict[int, SwissStanding]:
    lines = swiss_standings(
        entries,
        rounds,
        tiebreakers=tiebreakers,
        sit_out_points=sit_out_points,
        rng_seed=SEED,
    )
    return {standing.entry_id.int: standing for standing in lines}


def order(lines: Iterable[SwissStanding]) -> list[int]:
    return [standing.entry_id.int for standing in lines]


def pairs(draw: SwissDraw) -> list[tuple[int, int]]:
    return [(pair.side_1.int, pair.side_2.int) for pair in draw.pairs]


# Standings (BR-070 to BR-074, FR-043)


def test_br070_a_win_earns_2_a_draw_1_and_a_loss_0() -> None:
    rounds = [round_(1, match(1, 2, WIN), match(3, 4, DRAW), match(5, 6, LOSS))]

    lines = standings(ids(1, 2, 3, 4, 5, 6), rounds)

    assert {n: s.points for n, s in lines.items()} == {
        1: 2,
        2: 0,
        3: 1,
        4: 1,
        5: 0,
        6: 2,
    }
    assert [(lines[n].won, lines[n].drawn, lines[n].lost) for n in (1, 3, 5)] == [
        (1, 0, 0),
        (0, 1, 0),
        (0, 0, 1),
    ]


@pytest.mark.parametrize("sit_out_points", [0, 1])
def test_br071_a_sit_out_earns_the_sit_out_points(sit_out_points: int) -> None:
    rounds = [round_(1, match(1, 2, WIN), sat_out=3)]

    lines = standings(ids(1, 2, 3), rounds, sit_out_points=sit_out_points)

    assert lines[3].points == sit_out_points
    assert lines[3].sat_out == 1
    assert lines[3].played == 0


def test_br073_bh1_sums_the_opponents_points_and_bh2_their_bh1() -> None:
    rounds = [
        round_(1, match(1, 2, WIN), match(3, 4, DRAW)),
        round_(2, match(1, 3, WIN), match(2, 4, WIN)),
    ]

    lines = standings(ids(1, 2, 3, 4), rounds)

    assert {n: s.points for n, s in lines.items()} == {1: 4, 2: 2, 3: 1, 4: 1}
    assert {n: s.bh1 for n, s in lines.items()} == {1: 3, 2: 5, 3: 5, 4: 3}
    assert {n: s.bh2 for n, s in lines.items()} == {1: 10, 2: 6, 3: 6, 4: 10}


def test_br073_an_opponent_met_twice_counts_once_per_match() -> None:
    rounds = [round_(1, match(1, 2, WIN)), round_(2, match(2, 1, WIN))]

    lines = standings(ids(1, 2), rounds)

    assert lines[1].bh1 == 2 * lines[2].points


def test_br073_sit_outs_add_nothing_to_bh() -> None:
    rounds = [
        round_(1, match(1, 2, WIN), sat_out=3),
        round_(2, match(3, 1, WIN), sat_out=2),
    ]

    lines = standings(ids(1, 2, 3), rounds, sit_out_points=1)

    assert lines[3].bh1 == lines[1].points
    assert lines[2].bh1 == lines[1].points
    assert lines[1].bh1 == lines[2].points + lines[3].points


def test_br073_score_difference_counts_both_sides() -> None:
    rounds = [
        round_(1, match(1, 2, WIN, 3)),
        round_(2, match(2, 1, WIN, 2)),
    ]

    lines = standings(ids(1, 2), rounds)

    assert (lines[1].score_difference, lines[2].score_difference) == (1, -1)


def test_br073_a_match_without_a_result_counts_for_nothing() -> None:
    rounds = [round_(1, match(1, 2, None, 5))]

    lines = standings(ids(1, 2), rounds)

    assert [
        (s.points, s.played, s.bh1, s.score_difference) for s in lines.values()
    ] == [
        (0, 0, 0, 0),
        (0, 0, 0, 0),
    ]


def test_br064_a_missed_round_earns_nothing_and_is_no_sit_out() -> None:
    rounds = [round_(1, match(1, 2, WIN))]

    lines = standings(ids(1, 2, 3), rounds, sit_out_points=1)

    assert (lines[3].points, lines[3].sat_out, lines[3].played) == (0, 0, 0)


# Entries 1 and 2 have 3 points each: 1 has the better BH1 (5 v 3), 2 the better
# score difference (5 v 1).
TIED_ROUNDS = [
    round_(1, match(1, 3, WIN, 1), match(2, 4, WIN, 5)),
    round_(2, match(1, 2, DRAW), match(3, 4, WIN)),
]


@pytest.mark.parametrize(
    ("tiebreakers", "expected"),
    [
        pytest.param(
            (Tiebreaker.BH1, Tiebreaker.SCORE_DIFFERENCE), [1, 2], id="BH1-first"
        ),
        pytest.param(
            (Tiebreaker.SCORE_DIFFERENCE, Tiebreaker.BH1), [2, 1], id="score-first"
        ),
    ],
)
def test_br072_level_entries_follow_the_tiebreakers_in_order(
    tiebreakers: tuple[Tiebreaker, ...], expected: list[int]
) -> None:
    lines = swiss_standings(
        ids(1, 2, 3, 4),
        TIED_ROUNDS,
        tiebreakers=tiebreakers,
        sit_out_points=0,
        rng_seed=SEED,
    )

    assert order(lines)[:2] == expected
    assert [s.place for s in lines[:2]] == [1, 2]


def test_br072_points_come_before_every_tiebreaker() -> None:
    lines = standings(ids(1, 2, 3, 4), TIED_ROUNDS)

    assert (lines[3].position, lines[4].position) == (3, 4)
    assert lines[3].bh1 < lines[4].bh1


def test_fr043_entries_level_on_every_enabled_tiebreaker_share_the_place() -> None:
    lines = swiss_standings(
        ids(1, 2, 3, 4), TIED_ROUNDS, tiebreakers=(), sit_out_points=0, rng_seed=SEED
    )

    assert [(s.place, s.is_decided_by_lot) for s in lines[:2]] == [
        (1, True),
        (1, True),
    ]
    lot = order_by_lot(ids(1, 2), rng_seed=SEED, purpose="tiebreak:after-round-2")
    assert [s.entry_id for s in lines[:2]] == list(lot)


def test_br074_the_lot_orders_level_entries_by_the_completed_rounds() -> None:
    entries = ids(*range(1, 9))
    one = [round_(1, *(match(n, n + 1, DRAW) for n in range(1, 9, 2)))]
    two = [*one, round_(2, *(match(n, n + 2, DRAW) for n in (1, 2, 5, 6)))]
    unfinished = [*one, round_(2, match(1, 3, None))]

    after_one = swiss_standings(
        entries, one, tiebreakers=(), sit_out_points=0, rng_seed=SEED
    )
    after_two = swiss_standings(
        entries, two, tiebreakers=(), sit_out_points=0, rng_seed=SEED
    )
    during_two = swiss_standings(
        entries, unfinished, tiebreakers=(), sit_out_points=0, rng_seed=SEED
    )

    for lines, completed in ((after_one, 1), (after_two, 2), (during_two, 1)):
        expected = order_by_lot(
            entries, rng_seed=SEED, purpose=tiebreak_purpose(completed)
        )
        assert [s.entry_id for s in lines] == list(expected)
        assert {s.place for s in lines} == {1}
    assert order(after_one) != order(after_two)


def test_br074_the_tie_lot_is_named_after_the_completed_rounds() -> None:
    assert tiebreak_purpose(3) == "tiebreak:after-round-3"


@pytest.mark.parametrize(
    ("entries", "rounds", "tiebreakers", "sit_out_points", "message"),
    [
        pytest.param(ids(1, 1), [], (), 0, "twice", id="entry-twice"),
        pytest.param(
            ids(1), [], (Tiebreaker.BH1,) * 2, 0, "name one twice", id="tiebreaker"
        ),
        pytest.param(ids(1), [], (), 2, "0 or 1", id="sit-out-points"),
        pytest.param(
            ids(1, 2), [round_(2, match(1, 2))], (), 0, "1 to n", id="round-gap"
        ),
        pytest.param(
            ids(1, 2, 3),
            [round_(1, match(1, 2), sat_out=1)],
            (),
            0,
            "twice",
            id="twice-in-a-round",
        ),
        pytest.param(
            ids(1, 2), [round_(1, match(1, 9))], (), 0, "not given", id="unknown"
        ),
    ],
)
def test_swiss_standings_refuse_a_caller_bug(
    entries: list[EntryId],
    rounds: list[SwissRound],
    tiebreakers: tuple[Tiebreaker, ...],
    sit_out_points: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        swiss_standings(
            entries,
            rounds,
            tiebreakers=tiebreakers,
            sit_out_points=sit_out_points,
            rng_seed=SEED,
        )


# Round 1 (BR-055, BR-058)


def test_br055_eight_entries_play_1v5_2v6_3v7_4v8() -> None:
    draw = draw_first_swiss_round(ids(*range(1, 9)))

    assert pairs(draw) == [(1, 5), (2, 6), (3, 7), (4, 8)]
    assert (draw.round_no, draw.method, draw.sitting_out) == (
        1,
        PairingMethod.SEEDS,
        None,
    )


def test_br058_with_an_odd_count_the_lowest_seed_sits_out_round_1() -> None:
    draw = draw_first_swiss_round(ids(*range(1, 8)))

    assert draw.sitting_out == eid(7)
    assert pairs(draw) == [(1, 4), (2, 5), (3, 6)]
    assert not draw.is_sit_out_by_lot


@pytest.mark.parametrize("count", [0, 1])
def test_fr032_round_1_needs_two_entries(count: int) -> None:
    with pytest.raises(NotEnoughEntriesError) as raised:
        draw_first_swiss_round(ids(*range(1, count + 1)))

    assert (raised.value.minimum, raised.value.given) == (2, count)


def test_draw_first_swiss_round_refuses_an_entry_twice() -> None:
    with pytest.raises(ValueError, match="twice"):
        draw_first_swiss_round(ids(1, 2, 1))


# Later rounds (BR-056 to BR-058, ADR-011)


def test_br056_each_entry_plays_its_neighbour() -> None:
    draw = draw_next_swiss_round(table(4, 2, 3, 1), met((1, 2), (3, 4)))

    assert pairs(draw) == [(4, 2), (3, 1)]
    assert (draw.round_no, draw.method) == (3, PairingMethod.NEIGHBOURS)


def test_br056_an_entry_that_played_its_neighbour_plays_the_next_one_down() -> None:
    draw = draw_next_swiss_round(table(1, 2, 3, 4), met((1, 2), (3, 4)))

    assert pairs(draw) == [(1, 3), (2, 4)]
    assert not any(pair.is_repeat for pair in draw.pairs)


def test_adr011_when_br056_gets_stuck_the_whole_field_is_matched() -> None:
    # BR-056 pairs 1 v 2 and 3 v 4, and 5 and 6 have met.
    draw = draw_next_swiss_round(table(1, 2, 3, 4, 5, 6), met((5, 6)))

    assert draw.method is PairingMethod.MATCHING
    assert pairs(draw) == [(1, 2), (3, 5), (4, 6)]


def test_adr011_the_window_doubles_until_a_perfect_matching_exists() -> None:
    # Entry 1 has met the 16 entries below it, and 33 and 34 have met.
    history = met(*((1, n) for n in range(2, 18)), (33, 34))

    draw = draw_next_swiss_round(table(*range(1, 35)), history)

    assert draw.method is PairingMethod.MATCHING
    assert pairs(draw)[0] == (1, 18)
    assert not any(pair.is_repeat for pair in draw.pairs)


def test_br057_a_repeat_is_drawn_only_when_every_pairing_has_one() -> None:
    history = met((1, 2), (3, 4), (1, 3), (2, 4), (1, 4), (2, 3))

    draw = draw_next_swiss_round(table(1, 2, 3, 4), history)

    assert pairs(draw) == [(1, 2), (3, 4)]
    assert all(pair.is_repeat for pair in draw.pairs)


def test_br057_a_forced_draw_has_as_few_repeats_as_possible() -> None:
    history = met((1, 2), (3, 4), (1, 3), (2, 4), (2, 3))

    draw = draw_next_swiss_round(table(1, 2, 3, 4), history)

    assert pairs(draw) == [(1, 4), (2, 3)]
    assert [pair.is_repeat for pair in draw.pairs] == [False, True]


def test_br056_the_fallback_keeps_1st_v_2nd_when_a_repeat_free_draw_allows_it() -> None:
    # BR-056 gets stuck at 4 v 6, and the fallback must not split the leaders.
    history = met((3, 4), (4, 6))

    draw = draw_next_swiss_round(table(1, 2, 3, 4, 5, 6), history)

    assert draw.method is PairingMethod.MATCHING
    assert pairs(draw) == [(1, 2), (3, 6), (4, 5)]
    assert not any(pair.is_repeat for pair in draw.pairs)


def test_br057_a_forced_repeat_prefers_pairs_that_met_once_to_pairs_met_twice() -> None:
    history = met((1, 2), (1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4))

    draw = draw_next_swiss_round(table(1, 2, 3, 4), history)

    assert pairs(draw) == [(1, 3), (2, 4)]
    assert all(pair.is_repeat for pair in draw.pairs)


def test_br058_the_lowest_placed_of_those_with_fewest_sit_outs_sits_out() -> None:
    lines = [*table(1, 2, 3, 4), line(5, 5, sat_out=1)]

    draw = draw_next_swiss_round(lines, met((1, 2)))

    assert draw.sitting_out == eid(4)
    assert pairs(draw) == [(1, 3), (2, 5)]


def test_br058_the_lot_decides_the_sit_out_between_entries_sharing_a_place() -> None:
    lines = [*table(1, 2, 3), line(4, 4, place=4), line(5, 5, place=4)]

    draw = draw_next_swiss_round(lines, met((1, 2)))

    assert draw.sitting_out == eid(5)
    assert draw.is_sit_out_by_lot
    assert [pair.is_decided_by_lot for pair in draw.pairs] == [False, True]


def test_br058_a_lot_between_entries_with_other_sit_out_counts_decides_nothing() -> (
    None
):
    lines = [*table(1, 2), line(3, 3, place=3, sat_out=1), line(4, 4, place=3)]
    lines.append(line(5, 5, sat_out=1))

    draw = draw_next_swiss_round(lines, met((1, 2)))

    assert draw.sitting_out == eid(4)
    assert not draw.is_sit_out_by_lot


def test_br064_disabled_entries_are_not_drawn_and_do_not_sit_out() -> None:
    draw = draw_next_swiss_round(table(1, 2, 3, 4, 5), met((1, 2)), disabled=ids(5))

    assert draw.sitting_out is None
    assert pairs(draw) == [(1, 3), (2, 4)]


def test_br058_disabled_entries_do_not_count_for_the_sit_out() -> None:
    draw = draw_next_swiss_round(table(1, 2, 3, 4, 5), met((1, 2)), disabled=ids(5, 4))

    assert draw.sitting_out == eid(3)
    assert pairs(draw) == [(1, 2)]
    assert draw.pairs[0].is_repeat


@pytest.mark.parametrize("disabled", [ids(1, 2), ids(2)])
def test_fr044_a_round_needs_two_entries_that_are_not_disabled(
    disabled: list[EntryId],
) -> None:
    with pytest.raises(NotEnoughEntriesError) as raised:
        draw_next_swiss_round(table(1, 2), met((1, 2)), disabled=disabled)

    assert (raised.value.minimum, raised.value.given) == (2, 2 - len(disabled))


@pytest.mark.parametrize(
    ("lines", "rounds", "disabled", "message"),
    [
        pytest.param(table(1, 2), [], [], "from the seeds", id="no-round-yet"),
        pytest.param(table(1, 1), met((1, 2)), [], "twice", id="entry-twice"),
        pytest.param(
            [line(1, 1), line(2, 3)], met((1, 2)), [], "1 to n", id="position-gap"
        ),
        pytest.param(
            table(1, 2), [round_(1, match(1, 2, None))], [], "without", id="open"
        ),
        pytest.param(
            table(1, 2), met((1, 2)), ids(9), "not in the standing", id="disabled"
        ),
        pytest.param(table(1, 2), met((1, 9)), [], "not given", id="unknown"),
    ],
)
def test_draw_next_swiss_round_refuses_a_caller_bug(
    lines: list[SwissStanding],
    rounds: list[SwissRound],
    disabled: list[EntryId],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        draw_next_swiss_round(lines, rounds, disabled=disabled)


# Recommended minimum (BR-068)


@pytest.mark.parametrize(
    ("entries", "rounds"),
    [
        pytest.param(0, 0, id="none"),
        pytest.param(1, 0, id="one"),
        pytest.param(2, 1, id="two"),
        pytest.param(4, 2, id="four"),
        pytest.param(5, 3, id="BR-068-5"),
        pytest.param(8, 3, id="BR-068-8"),
        pytest.param(9, 4, id="BR-068-9"),
        pytest.param(16, 4, id="BR-068-16"),
        pytest.param(17, 5, id="BR-068-17"),
        pytest.param(32, 5, id="BR-068-32"),
        pytest.param(256, 8, id="FR-032-256"),
    ],
)
def test_br068_the_recommended_minimum_is_log2_rounded_up(
    entries: int, rounds: int
) -> None:
    assert recommended_minimum_rounds(entries) == rounds


def test_br068_a_negative_count_is_a_caller_bug() -> None:
    with pytest.raises(ValueError, match="negative"):
        recommended_minimum_rounds(-1)


@given(st.integers(min_value=2, max_value=10_000))
def test_br068_the_minimum_is_the_smallest_r_with_2_to_the_r_at_least_n(
    entries: int,
) -> None:
    rounds = recommended_minimum_rounds(entries)

    assert 2 ** (rounds - 1) < entries <= 2**rounds


# Properties


@st.composite
def histories(
    draw: st.DrawFn,
    *,
    max_entries: int = 32,
    max_rounds: int = 12,
    unfinished: bool = True,
) -> tuple[list[EntryId], list[SwissRound]]:
    """Entries and rounds: random pairings, results and absences.

    With `unfinished`, some matches have no result yet (a draw refuses those).
    """
    outcomes: list[MatchOutcome | None] = [*MatchOutcome]
    if unfinished:
        outcomes.append(None)
    count = draw(st.integers(min_value=2, max_value=max_entries))
    entries = ids(*range(1, count + 1))
    rounds: list[SwissRound] = []
    for round_no in range(1, draw(st.integers(1, min(max_rounds, count + 1))) + 1):
        shuffled = draw(st.permutations(entries))
        present = shuffled[draw(st.integers(0, min(2, count - 2))) :]
        sat_out = tuple(present[-1:]) if len(present) % 2 else ()
        playing = present[: len(present) - len(sat_out)]
        matches = tuple(
            SwissMatch(
                side_1=playing[index],
                side_2=playing[index + 1],
                outcome=draw(st.sampled_from(outcomes)),
                score_difference=draw(st.integers(-5, 5)),
            )
            for index in range(0, len(playing), 2)
        )
        rounds.append(SwissRound(round_no=round_no, matches=matches, sat_out=sat_out))
    return entries, rounds


tiebreaker_orders = st.lists(st.sampled_from(Tiebreaker), unique=True)
seeds = st.binary(min_size=16, max_size=16)


def met_pairs(rounds: Iterable[SwissRound]) -> set[frozenset[EntryId]]:
    return {
        frozenset((m.side_1, m.side_2)) for round_ in rounds for m in round_.matches
    }


def has_repeat_free_pairing(
    entries: Sequence[EntryId], met: set[frozenset[EntryId]]
) -> bool:
    """The oracle of ADR-011: brute force below 12 entries, else blossom."""
    if len(entries) < 12:
        return min_repeats(entries, met) == 0
    graph: nx.Graph[EntryId] = nx.Graph()
    graph.add_nodes_from(entries)
    graph.add_edges_from(
        (a, b) for a, b in combinations(entries, 2) if frozenset((a, b)) not in met
    )
    return 2 * len(nx.max_weight_matching(graph, maxcardinality=True)) == len(entries)


def min_repeats(entries: Sequence[EntryId], met: set[frozenset[EntryId]]) -> int:
    """The fewest repeats of any perfect matching, by brute force."""
    if not entries:
        return 0
    first, *rest = entries
    return min(
        (frozenset((first, other)) in met)
        + min_repeats([e for e in rest if e != other], met)
        for other in rest
    )


def neighbour_pairs(
    playing: Sequence[EntryId], met: set[frozenset[EntryId]]
) -> list[tuple[EntryId, EntryId]] | None:
    """BR-056 as the PRD writes it, independently of the engine."""
    left = list(playing)
    found: list[tuple[EntryId, EntryId]] = []
    while left:
        top = left.pop(0)
        below = [e for e in left if frozenset((top, e)) not in met]
        if not below:
            return None
        left.remove(below[0])
        found.append((top, below[0]))
    return found


@st.composite
def draws(
    draw: st.DrawFn, *, max_entries: int = 32
) -> tuple[list[SwissStanding], list[SwissRound], list[EntryId], SwissDraw]:
    entries, rounds = draw(histories(max_entries=max_entries, unfinished=False))
    lines = list(
        swiss_standings(
            entries,
            rounds,
            tiebreakers=draw(tiebreaker_orders),
            sit_out_points=draw(st.sampled_from((0, 1))),
            rng_seed=draw(seeds),
        )
    )
    disabled = draw(
        st.lists(st.sampled_from(entries), unique=True, max_size=len(entries) - 2)
    )
    return (
        lines,
        rounds,
        disabled,
        draw_next_swiss_round(lines, rounds, disabled=disabled),
    )


def playing_entries(
    lines: Sequence[SwissStanding], disabled: Iterable[EntryId], result: SwissDraw
) -> list[EntryId]:
    off = {*disabled, result.sitting_out}
    return [s.entry_id for s in lines if s.entry_id not in off]


@settings(deadline=None)
@given(draws())
def test_br057_no_repeat_while_a_pairing_without_one_exists(
    case: tuple[list[SwissStanding], list[SwissRound], list[EntryId], SwissDraw],
) -> None:
    lines, rounds, disabled, result = case
    playing = playing_entries(lines, disabled, result)

    has_repeat = any(pair.is_repeat for pair in result.pairs)

    assert has_repeat == (not has_repeat_free_pairing(playing, met_pairs(rounds)))


@settings(deadline=None)
@given(draws(max_entries=10))
def test_br057_a_forced_draw_has_the_fewest_repeats_possible(
    case: tuple[list[SwissStanding], list[SwissRound], list[EntryId], SwissDraw],
) -> None:
    lines, rounds, disabled, result = case
    playing = playing_entries(lines, disabled, result)
    met = met_pairs(rounds)

    repeats = sum(pair.is_repeat for pair in result.pairs)

    assert repeats == min_repeats(playing, met)
    assert all(
        pair.is_repeat == (frozenset((pair.side_1, pair.side_2)) in met)
        for pair in result.pairs
    )


def meetings(rounds: Iterable[SwissRound]) -> Counter[frozenset[EntryId]]:
    return Counter(
        frozenset((m.side_1, m.side_2)) for round_ in rounds for m in round_.matches
    )


def cheapest_cost(
    positions: Sequence[int], count: int, met: Counter[tuple[int, int]]
) -> tuple[int, int]:
    """The least (meetings, distance cost) of any perfect matching, by brute force.

    A pair of positions `top < bottom` costs `(bottom - top) ** 2 * (count - top)`.
    """
    if not positions:
        return (0, 0)
    top, *rest = positions
    return min(
        (
            met[(top, bottom)] + sub[0],
            (bottom - top) ** 2 * (count - top) + sub[1],
        )
        for bottom in rest
        for sub in [cheapest_cost([p for p in rest if p != bottom], count, met)]
    )


@settings(deadline=None)
@given(draws(max_entries=10))
def test_adr011_the_fallback_is_the_cheapest_matching_by_meetings_then_distance(
    case: tuple[list[SwissStanding], list[SwissRound], list[EntryId], SwissDraw],
) -> None:
    lines, rounds, disabled, result = case
    assume(result.method is PairingMethod.MATCHING)
    playing = playing_entries(lines, disabled, result)
    number = {entry: index for index, entry in enumerate(playing)}
    met = Counter(
        {
            (min(number[a], number[b]), max(number[a], number[b])): times
            for pair, times in meetings(rounds).items()
            if pair <= number.keys()
            for a, b in [tuple(pair)]
        }
    )
    count = len(playing)

    chosen = [
        sorted((number[pair.side_1], number[pair.side_2])) for pair in result.pairs
    ]

    assert (
        sum(met[(top, bottom)] for top, bottom in chosen),
        sum((bottom - top) ** 2 * (count - top) for top, bottom in chosen),
    ) == cheapest_cost(list(range(count)), count, met)


@settings(deadline=None)
@given(draws())
def test_br058_every_entry_plays_once_or_sits_out(
    case: tuple[list[SwissStanding], list[SwissRound], list[EntryId], SwissDraw],
) -> None:
    lines, rounds, disabled, result = case
    active = [s for s in lines if s.entry_id not in disabled]

    drawn = [side for pair in result.pairs for side in (pair.side_1, pair.side_2)]

    assert result.round_no == len(rounds) + 1
    assert (result.sitting_out is not None) == (len(active) % 2 == 1)
    assert Counter(drawn) == Counter(playing_entries(lines, disabled, result))
    if result.sitting_out is not None:
        # BR-058: the lowest-placed of those with the fewest sit-outs.
        fewest = min(s.sat_out for s in active)
        candidates = [s for s in active if s.sat_out == fewest]
        sitting = next(s for s in lines if s.entry_id == result.sitting_out)
        assert sitting in candidates
        assert all(sitting.place >= s.place for s in candidates)
        assert result.is_sit_out_by_lot == any(
            s.place == sitting.place for s in candidates if s is not sitting
        )


@settings(deadline=None)
@given(draws())
def test_br056_whenever_br056_completes_the_draw_is_br056(
    case: tuple[list[SwissStanding], list[SwissRound], list[EntryId], SwissDraw],
) -> None:
    lines, rounds, disabled, result = case
    playing = playing_entries(lines, disabled, result)

    expected = neighbour_pairs(playing, met_pairs(rounds))

    if expected is None:
        assert result.method is PairingMethod.MATCHING
    else:
        assert result.method is PairingMethod.NEIGHBOURS
        assert [(p.side_1, p.side_2) for p in result.pairs] == expected


@given(st.lists(st.integers(1, 5), min_size=1, max_size=5), st.data())
def test_br056_entries_level_on_points_play_each_other_when_they_can(
    halves: list[int], data: st.DataObject
) -> None:
    # Score groups of even size, best first, whose members have not met.
    group_of: dict[int, int] = {}
    for group, half in enumerate(halves):
        for _ in range(2 * half):
            group_of[len(group_of) + 1] = group
    lines = [line(n, n, points=len(halves) - group) for n, group in group_of.items()]
    across = [
        (a, b) for a, b in combinations(group_of, 2) if group_of[a] != group_of[b]
    ]
    chosen = data.draw(st.lists(st.sampled_from(across), unique=True)) if across else []
    history = [round_(1), *(round_(n, match(*p)) for n, p in enumerate(chosen, 2))]

    result = draw_next_swiss_round(lines, history)

    assert result.method is PairingMethod.NEIGHBOURS
    assert all(group_of[p.side_1.int] == group_of[p.side_2.int] for p in result.pairs)


@settings(deadline=None)
@given(histories(), tiebreaker_orders, st.sampled_from((0, 1)), seeds, st.data())
def test_adr010_draws_and_standings_do_not_depend_on_input_order(
    history: tuple[list[EntryId], list[SwissRound]],
    tiebreakers: list[Tiebreaker],
    sit_out_points: int,
    seed: bytes,
    data: st.DataObject,
) -> None:
    entries, rounds = history
    disabled = data.draw(
        st.lists(st.sampled_from(entries), unique=True, max_size=len(entries) - 2)
    )
    is_finished = all(m.outcome is not None for r in rounds for m in r.matches)
    shuffled_rounds = [
        SwissRound(
            round_no=r.round_no,
            matches=tuple(data.draw(st.permutations(r.matches))),
            sat_out=r.sat_out,
        )
        for r in data.draw(st.permutations(rounds))
    ]

    def run(
        entries: Iterable[EntryId],
        rounds: list[SwissRound],
        disabled: list[EntryId],
        *,
        shuffle: bool,
    ) -> tuple[tuple[SwissStanding, ...], SwissDraw | None]:
        lines = swiss_standings(
            entries,
            rounds,
            tiebreakers=tiebreakers,
            sit_out_points=sit_out_points,
            rng_seed=seed,
        )
        if not is_finished:
            return lines, None  # a draw refuses a match without a result
        given_lines = data.draw(st.permutations(lines)) if shuffle else lines
        return lines, draw_next_swiss_round(given_lines, rounds, disabled=disabled)

    assert run(entries, rounds, disabled, shuffle=False) == run(
        entries, rounds, disabled, shuffle=False
    )
    assert run(entries, rounds, disabled, shuffle=False) == run(
        data.draw(st.permutations(entries)),
        shuffled_rounds,
        data.draw(st.permutations(disabled)),
        shuffle=True,
    )


@given(histories(), tiebreaker_orders, st.sampled_from((0, 1)), seeds)
def test_br073_bh_sums_are_consistent(
    history: tuple[list[EntryId], list[SwissRound]],
    tiebreakers: list[Tiebreaker],
    sit_out_points: int,
    seed: bytes,
) -> None:
    entries, rounds = history

    lines = swiss_standings(
        entries,
        rounds,
        tiebreakers=tiebreakers,
        sit_out_points=sit_out_points,
        rng_seed=seed,
    )

    by_id = {s.entry_id: s for s in lines}
    results = [m for r in rounds for m in r.matches if m.outcome is not None]
    sit_outs = sum(len(r.sat_out) for r in rounds)
    assert sum(s.points for s in lines) == 2 * len(results) + sit_out_points * sit_outs
    assert sum(s.bh1 for s in lines) == sum(s.points * s.played for s in lines)
    assert sum(s.bh2 for s in lines) == sum(s.bh1 * s.played for s in lines)
    assert sum(s.score_difference for s in lines) == 0
    for s in lines:
        opponents = [
            m.side_2 if m.side_1 == s.entry_id else m.side_1
            for m in results
            if s.entry_id in {m.side_1, m.side_2}
        ]
        assert s.bh1 == sum(by_id[o].points for o in opponents)
        assert s.bh2 == sum(by_id[o].bh1 for o in opponents)
        assert s.played == s.won + s.drawn + s.lost == len(opponents)


@given(histories(), tiebreaker_orders, seeds)
def test_br074_positions_are_strict_and_level_entries_share_the_place(
    history: tuple[list[EntryId], list[SwissRound]],
    tiebreakers: list[Tiebreaker],
    seed: bytes,
) -> None:
    entries, rounds = history

    lines = swiss_standings(
        entries, rounds, tiebreakers=tiebreakers, sit_out_points=0, rng_seed=seed
    )

    def criteria(s: SwissStanding) -> tuple[int, ...]:
        values = {
            Tiebreaker.BH1: s.bh1,
            Tiebreaker.BH2: s.bh2,
            Tiebreaker.SCORE_DIFFERENCE: s.score_difference,
        }
        return (s.points, *(values[t] for t in tiebreakers))

    assert [s.position for s in lines] == list(range(1, len(entries) + 1))
    assert [criteria(s) for s in lines] == sorted(map(criteria, lines), reverse=True)
    for s in lines:
        level = [o for o in lines if criteria(o) == criteria(s)]
        assert s.place == level[0].position
        assert s.is_decided_by_lot == (len(level) > 1)


@given(st.integers(min_value=2, max_value=64))
def test_br055_round_1_pairs_the_top_half_against_the_bottom_half(count: int) -> None:
    seeds = ids(*range(1, count + 1))

    result = draw_first_swiss_round(seeds)

    half = count // 2
    assert pairs(result) == [(n, n + half) for n in range(1, half + 1)]
    assert result.sitting_out == (eid(count) if count % 2 else None)


def play(result: SwissDraw, round_no: int) -> SwissRound:
    """Side 1 wins, with a score difference that varies by entry."""
    return SwissRound(
        round_no=round_no,
        matches=tuple(
            SwissMatch(
                side_1=pair.side_1,
                side_2=pair.side_2,
                outcome=WIN if (pair.side_1.int + round_no) % 3 else DRAW,
                score_difference=pair.side_2.int % 4,
            )
            for pair in result.pairs
        ),
        sat_out=() if result.sitting_out is None else (result.sitting_out,),
    )


def run_swiss(count: int, round_count: int, seed: bytes) -> list[SwissRound]:
    entries = ids(*range(1, count + 1))
    rounds = [play(draw_first_swiss_round(entries), 1)]
    for round_no in range(2, round_count + 1):
        lines = swiss_standings(
            entries,
            rounds,
            tiebreakers=DEFAULT_TIEBREAKERS,
            sit_out_points=0,
            rng_seed=seed,
        )
        rounds.append(play(draw_next_swiss_round(lines, rounds), round_no))
    return rounds


@settings(deadline=None)
@given(st.integers(min_value=2, max_value=24), st.integers(1, 12), seeds)
@example(count=7, round_count=8, seed=SEED)
def test_adr011_a_whole_swiss_repeats_nobody_while_dirac_allows_it(
    count: int, round_count: int, seed: bytes
) -> None:
    rounds = run_swiss(count, round_count, seed)

    seen: set[frozenset[EntryId]] = set()
    for done, round_ in enumerate(rounds):
        pairs_now = [frozenset((m.side_1, m.side_2)) for m in round_.matches]
        if 2 * len(pairs_now) >= 2 * done + 2:
            assert seen.isdisjoint(pairs_now)
        seen.update(pairs_now)
    sat_out = Counter(e for r in rounds for e in r.sat_out)
    counts = [sat_out[e] for e in ids(*range(1, count + 1))]
    assert max(counts) - min(counts) <= 1


@pytest.mark.benchmark
def test_adr011_benchmark_64_entries_over_7_rounds_take_under_a_second() -> None:
    start = perf_counter()
    rounds = run_swiss(64, 7, SEED)
    elapsed = perf_counter() - start

    assert len(rounds) == 7
    assert elapsed < 1.0
