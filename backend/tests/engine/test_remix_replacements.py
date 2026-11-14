"""Replacements in a Lord have mercy knockout (BR-147 to BR-149, BR-151 to BR-157).

The PRD's worked case below §7.17 and its four variants are exact test
vectors. #n is the player placed nth after the group phase: here player n,
alone at place n of the standing.
"""

from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import replace
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tourneyhub.engine.ids import EntryId, PlayerId
from tourneyhub.engine.knockout import MatchKey, draw_bracket
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.places import PlacingEntry
from tourneyhub.engine.remix import (
    REPLACEMENT_PURPOSE,
    RemixMatch,
    RemixPlace,
    RemixState,
    Replacement,
    ReplacementPlan,
    draw_next_round,
    place_remix_players,
    plan_replacements,
    players_who_left,
    remix_season_points,
    remix_state,
)
from tourneyhub.engine.tournaments import Outcome

SEED = bytes(range(16))
DEFAULT_TABLE = [10, 8, 6, 4, 2]  # FR-011
W1, W2 = Outcome.SIDE_1, Outcome.SIDE_2

type Pair = tuple[int, int]


def pid(n: int) -> PlayerId:
    return PlayerId(UUID(int=n))


def eid(n: int) -> EntryId:
    return EntryId(UUID(int=1000 + n))


def came_in(player: int, replaced: int) -> Replacement:
    return Replacement(player_id=pid(player), replaced_player_id=pid(replaced))


def match(
    round_no: int,
    position: int,
    side_1: Pair | None,
    side_2: Pair | None,
    outcome: Outcome | None = None,
    *,
    third: bool = False,
    replacements: Iterable[Replacement] = (),
) -> RemixMatch:
    return RemixMatch(
        key=MatchKey(round_no=round_no, is_third_place=third, position=position),
        side_1=None if side_1 is None else (pid(side_1[0]), pid(side_1[1])),
        side_2=None if side_2 is None else (pid(side_2[0]), pid(side_2[1])),
        outcome=outcome,
        replacements=tuple(sorted(replacements, key=lambda r: r.player_id)),
    )


def ints(players: Iterable[PlayerId]) -> set[int]:
    return {player_id.int for player_id in players}


def players_of(matches: Iterable[RemixMatch]) -> set[int]:
    return {p.int for m in matches for p in m.players}


def standing(players: Iterable[int] = range(1, 17)) -> list[list[PlayerId]]:
    """A group-phase standing with player n alone at place n."""
    return [[pid(n)] for n in players]


def plan(
    state: RemixState,
    disabled: Iterable[int],
    order: Sequence[Sequence[PlayerId]] | None = None,
) -> ReplacementPlan:
    return plan_replacements(
        state,
        disabled=[pid(n) for n in disabled],
        standing=standing() if order is None else order,
        rng_seed=SEED,
    )


def as_ints(planned: ReplacementPlan) -> tuple[list[Pair], list[int]]:
    """(came in, for whom) pairs and the players staying without one."""
    return (
        [(r.player_id.int, r.replaced_player_id.int) for r in planned.replacements],
        [p.int for p in planned.staying],
    )


def draw(state: RemixState, disabled: Iterable[int]) -> tuple[RemixMatch, ...]:
    return draw_next_round(
        state, rng_seed=SEED, disabled=[pid(n) for n in disabled], standing=standing()
    )


def places(
    state: RemixState, players: Iterable[int] = range(1, 17)
) -> tuple[RemixPlace, ...]:
    players = list(players)
    return place_remix_players(
        state,
        entries=[
            PlacingEntry(entry_id=eid(n), player_ids=(pid(n),), seed=n) for n in players
        ],
        standing=[[eid(n)] for n in players],
    )


def place_of(rows: Iterable[RemixPlace]) -> dict[int, int]:
    return {row.player_id.int: row.place for row in rows}


def partner_of(rows: Iterable[RemixPlace]) -> dict[int, int | None]:
    return {
        row.player_id.int: None if row.partner_id is None else row.partner_id.int
        for row in rows
    }


# The worked case: 16 players, a third-place match. Step 1, the quarterfinals:
# the pairs of #1, #2, #3, #4, #9, #10, #11 and #12 win.
QUARTERFINALS = [
    match(1, 1, (1, 9), (5, 13), W1),
    match(1, 2, (2, 10), (6, 14), W1),
    match(1, 3, (3, 11), (7, 15), W1),
    match(1, 4, (4, 12), (8, 16), W1),
]
# Step 3, the semifinals, drawn with #6 in for #3: the pairs of #1, #2, #6
# and #9 win; #4, #10, #11 and #12 wait for the third-place match.
SEMIFINALS = [
    match(2, 1, (1, 6), (4, 10), W1, replacements=[came_in(6, 3)]),
    match(2, 2, (2, 9), (11, 12), W1),
]
# Step 5, with #7 in for #2: the pair of #1 and #6 beats #7 and #9, the pair
# of #4 and #10 beats #11 and #12.
FINALS = [
    match(3, 1, (1, 6), (7, 9), W1, replacements=[came_in(7, 2)]),
    match(3, 1, (4, 10), (11, 12), W1, third=True),
]


def state_of(
    matches: Iterable[RemixMatch], *, third_place_match: bool = True
) -> RemixState:
    return remix_state(matches, third_place_match=third_place_match)


# The worked case, step by step (BR-145, BR-147, BR-148, BR-151)


def test_br147_br148_worked_case_step_2_6_comes_in_for_3_and_5_is_skipped() -> None:
    state = state_of(QUARTERFINALS)

    planned = plan(state, disabled=[3, 5])

    assert as_ints(planned) == ([(6, 3)], [])


def test_br156_worked_case_step_2_the_semifinals_are_drawn_from_the_new_pool() -> None:
    drawn = draw(state_of(QUARTERFINALS), disabled=[3, 5])

    assert players_of(drawn) == {1, 2, 4, 6, 9, 10, 11, 12}
    assert [r for m in drawn for r in m.replacements] == [came_in(6, 3)]
    assert next(m for m in drawn if pid(6) in m.players).replacements == (
        came_in(6, 3),
    )


def test_br147_worked_case_step_3_the_semifinal_losers_are_still_in() -> None:
    state = state_of([*QUARTERFINALS, *SEMIFINALS])

    assert ints(state.still_in) == {1, 2, 4, 6, 9, 10, 11, 12}
    assert ints(state.replaced) == {3}
    assert ints(state.knocked_out) == {5, 7, 8, 13, 14, 15, 16}


def test_br148_worked_case_step_4_7_comes_in_for_2() -> None:
    state = state_of([*QUARTERFINALS, *SEMIFINALS])

    planned = plan(state, disabled=[2, 3, 5])

    assert as_ints(planned) == ([(7, 2)], [])


def test_br144_br156_worked_case_step_5_the_final_pools() -> None:
    drawn = draw(state_of([*QUARTERFINALS, *SEMIFINALS]), disabled=[2, 3, 5])

    final = [m for m in drawn if not m.key.is_third_place]
    third = [m for m in drawn if m.key.is_third_place]
    assert players_of(final) == {1, 6, 7, 9}
    assert final[0].replacements == (came_in(7, 2),)
    assert players_of(third) == {4, 10, 11, 12}
    assert third[0].replacements == ()


def test_br145_br151_worked_case_step_6_places() -> None:
    rows = places(state_of([*QUARTERFINALS, *SEMIFINALS, *FINALS]))

    assert place_of(rows) == {
        1: 1, 6: 1, 7: 2, 9: 2, 4: 3, 10: 3, 11: 4, 12: 4,
        3: 5, 2: 5, 5: 5, 8: 5, 13: 5, 14: 5, 15: 5, 16: 5,
    }  # fmt: skip
    assert sorted(Counter(row.place for row in rows).values(), reverse=True) == [
        8,
        2,
        2,
        2,
        2,
    ]


def test_br151_worked_case_step_6_3_and_2_take_the_seats_given_up() -> None:
    rows = places(state_of([*QUARTERFINALS, *SEMIFINALS, *FINALS]))

    partners = partner_of(rows)
    seat_round = {row.player_id.int: row.seat_round_no for row in rows}
    assert (partners[3], partners[14]) == (14, 3)  # #6's quarterfinal seat
    assert (partners[2], partners[15]) == (15, 2)  # #7's quarterfinal seat
    assert (seat_round[3], seat_round[2]) == (1, 1)
    assert {n for n, r in seat_round.items() if r is not None} == {2, 3}


def test_br111_worked_case_step_6_points() -> None:
    rows = places(state_of([*QUARTERFINALS, *SEMIFINALS, *FINALS]))

    points = {
        row.player_id.int: row.points
        for row in remix_season_points(rows, DEFAULT_TABLE)
    }

    assert points == {
        1: 10, 6: 10, 7: 8, 9: 8, 4: 6, 10: 6, 11: 4, 12: 4,
        3: 0, 2: 0, 5: 0, 8: 0, 13: 0, 14: 0, 15: 0, 16: 0,
    }  # fmt: skip


# The four variants


def test_br152_variant_1_2_leaves_after_the_draw_and_loses_by_walkover() -> None:
    before_final = state_of([*QUARTERFINALS, *SEMIFINALS])
    drawn = draw(before_final, disabled=[3, 5])
    final = [
        match(3, 1, (1, 6), (2, 9), W1),  # the walkover against #2's pair
        match(3, 1, (4, 10), (11, 12), W1, third=True),
    ]

    state = state_of([*QUARTERFINALS, *SEMIFINALS, *final])

    assert players_of(m for m in drawn if not m.key.is_third_place) == {1, 2, 6, 9}
    assert ints(
        players_who_left(state_of([*QUARTERFINALS, *SEMIFINALS, *drawn]), [pid(2)])
    ) == {2}
    assert place_of(places(state))[2] == 2


def test_br152_br156_variant_1_drawn_again_7_comes_in_third_place_stays() -> None:
    before_final = state_of([*QUARTERFINALS, *SEMIFINALS])
    first = draw(before_final, disabled=[3, 5])

    again = draw(before_final, disabled=[2, 3, 5])

    assert players_of(m for m in again if not m.key.is_third_place) == {1, 6, 7, 9}
    assert [m for m in again if m.key.is_third_place] == [
        m for m in first if m.key.is_third_place
    ]


def test_br153_variant_2_re_enabling_2_changes_nothing() -> None:
    state = state_of([*QUARTERFINALS, *SEMIFINALS, *FINALS])

    assert pid(2) not in state.still_in | state.knocked_out
    assert players_who_left(state, [pid(2)]) == frozenset()
    assert place_of(places(state))[2] == 5


def test_br154_variant_2_deleting_the_last_round_undoes_the_replacement() -> None:
    before_final = state_of([*QUARTERFINALS, *SEMIFINALS])

    drawn = draw(before_final, disabled=[3, 5])  # #2 is re-enabled

    assert pid(7) in before_final.knocked_out
    assert players_of(m for m in drawn if not m.key.is_third_place) == {1, 2, 6, 9}
    assert all(m.replacements == () for m in drawn)


def test_br154_a_player_still_disabled_is_replaced_again() -> None:
    before_final = state_of([*QUARTERFINALS, *SEMIFINALS])

    drawn = draw(before_final, disabled=[2, 3, 5])

    assert drawn == draw(before_final, disabled=[2, 3, 5])
    assert [r for m in drawn for r in m.replacements] == [came_in(7, 2)]


GONE_HOME = [3, 5, 8, 13, 14, 15, 16]  # everybody knocked out except #7


def test_br148_br149_variant_3_too_few_replacements() -> None:
    state = state_of([*QUARTERFINALS, *SEMIFINALS])

    planned = plan(state, disabled=[1, 2, *GONE_HOME])

    assert as_ints(planned) == ([(7, 2)], [1])


def test_br148_br149_variant_3_draw_walkover_and_places() -> None:
    drawn = draw(state_of([*QUARTERFINALS, *SEMIFINALS]), disabled=[1, 2, *GONE_HOME])
    final = [
        match(3, 1, (6, 7), (1, 9), W1, replacements=[came_in(7, 2)]),
        match(3, 1, (4, 10), (11, 12), W1, third=True),
    ]

    rows = places(state_of([*QUARTERFINALS, *SEMIFINALS, *final]))

    assert players_of(m for m in drawn if not m.key.is_third_place) == {1, 6, 7, 9}
    assert place_of(rows)[1] == 2
    assert place_of(rows)[2] == 5


def test_br149_br157_variant_4_nobody_available() -> None:
    state = state_of([*QUARTERFINALS, *SEMIFINALS])

    planned = plan(state, disabled=[1, 2, 7, *GONE_HOME])
    drawn = draw(state, disabled=[1, 2, 7, *GONE_HOME])

    assert as_ints(planned) == ([], [1, 2])
    assert players_of(m for m in drawn if not m.key.is_third_place) == {1, 2, 6, 9}
    assert all(m.replacements == () for m in drawn)


def test_br145_br157_variant_4_both_take_the_places_of_their_pairs() -> None:
    final = [
        match(3, 1, (1, 6), (2, 9), W2),  # the organizer picks the pair of #2
        match(3, 1, (4, 10), (11, 12), W1, third=True),
    ]

    rows = places(state_of([*QUARTERFINALS, *SEMIFINALS, *final]))

    assert (place_of(rows)[1], place_of(rows)[2]) == (2, 1)


# Candidates and the order of the plan (BR-148)


def test_br148_before_the_final_of_4_pairs_with_third_place_nobody_is_available() -> (
    None
):
    semifinals = [match(1, 1, (1, 2), (3, 4), W1), match(1, 2, (5, 6), (7, 8), W2)]

    planned = plan(state_of(semifinals), disabled=[1], order=standing(range(1, 9)))

    assert as_ints(planned) == ([], [1])


def test_br148_without_third_place_the_semifinal_losers_come_first() -> None:
    semifinals = [
        match(2, 1, (1, 6), (4, 10), W1, replacements=[came_in(6, 3)]),
        match(2, 2, (2, 9), (11, 12), W1),
    ]
    state = state_of([*QUARTERFINALS, *semifinals], third_place_match=False)

    planned = plan(state, disabled=[1])

    assert as_ints(planned) == ([(4, 1)], [])


def test_br148_the_lot_breaks_a_tie_in_the_standing() -> None:
    tied = [[pid(n)] for n in range(1, 5)] + [[pid(5), pid(6), pid(7), pid(8)]]
    tied += [[pid(n)] for n in range(9, 17)]
    first = order_by_lot(
        [pid(n) for n in (5, 6, 7, 8)], rng_seed=SEED, purpose=REPLACEMENT_PURPOSE
    )[0]

    planned = plan(state_of(QUARTERFINALS), disabled=[3], order=tied)

    assert planned.replacements == (
        Replacement(player_id=first, replaced_player_id=pid(3)),
    )


def test_br148_the_better_standing_gets_the_better_replacement() -> None:
    planned = plan(state_of(QUARTERFINALS), disabled=[12, 2, 9])

    assert as_ints(planned) == ([(5, 2), (6, 9), (7, 12)], [])


def test_br148_tied_players_who_left_are_ordered_by_the_lot() -> None:
    tied = [[pid(1), pid(2)], *standing(range(3, 17))]
    first, second = order_by_lot(
        [pid(1), pid(2)], rng_seed=SEED, purpose=REPLACEMENT_PURPOSE
    )

    planned = plan(state_of(QUARTERFINALS), disabled=[1, 2], order=tied)

    assert [r.replaced_player_id for r in planned.replacements] == [first, second]


def test_br148_a_player_missing_from_the_standing_comes_last() -> None:
    planned = plan(state_of(QUARTERFINALS), disabled=[3], order=standing(range(6, 17)))

    assert as_ints(planned) == ([(6, 3)], [])


def test_br148_never_a_non_qualifier() -> None:
    order = [[pid(99)], *standing()]

    planned = plan(state_of(QUARTERFINALS), disabled=[1], order=order)

    assert as_ints(planned) == ([(5, 1)], [])


def test_br148_a_semifinal_loser_who_left_is_replaced_in_the_third_place_match() -> (
    None
):
    state = state_of([*QUARTERFINALS, *SEMIFINALS])

    drawn = draw(state, disabled=[3, 5, 10])

    third = next(m for m in drawn if m.key.is_third_place)
    assert players_of([third]) == {4, 7, 11, 12}
    assert third.replacements == (came_in(7, 10),)


def test_br148_the_plan_needs_a_round_to_draw() -> None:
    state = state_of([*QUARTERFINALS, *SEMIFINALS, *FINALS])

    with pytest.raises(ValueError, match="cannot be drawn"):
        plan(state, disabled=[1])


def test_br153_a_replaced_player_is_never_picked_again() -> None:
    semifinals = [
        match(2, 1, (1, 6), (4, 10), W2, replacements=[came_in(6, 3)]),
        match(2, 2, (2, 9), (11, 12), W1),
    ]
    state = state_of([*QUARTERFINALS, *semifinals], third_place_match=False)

    planned = plan(state, disabled=[2])  # #3 re-enabled

    assert pid(3) not in state.knocked_out
    assert as_ints(planned) == ([(1, 2)], [])


def test_br147_br153_a_replaced_winner_is_not_still_in() -> None:
    state = state_of([*QUARTERFINALS, *SEMIFINALS])

    assert pid(3) not in state.still_in
    assert players_who_left(state, [pid(3)]) == frozenset()


# Places of chains of replacements (BR-151)


def test_br151_a_replacement_who_wins_and_is_later_replaced() -> None:
    semifinals = [
        match(2, 1, (1, 5), (4, 10), W1, replacements=[came_in(5, 3)]),
        match(2, 2, (2, 9), (11, 12), W1),
    ]
    final = [match(3, 1, (1, 4), (2, 9), W1, replacements=[came_in(4, 5)])]
    state = state_of([*QUARTERFINALS, *semifinals, *final], third_place_match=False)

    rows = places(state)

    assert place_of(rows) == {
        1: 1, 4: 1, 2: 2, 9: 2, 5: 3, 10: 3, 11: 3, 12: 3,
        3: 5, 13: 5, 6: 5, 14: 5, 7: 5, 15: 5, 8: 5, 16: 5,
    }  # fmt: skip
    assert partner_of(rows)[5] == 10
    assert partner_of(rows)[3] == 13
    assert {row.player_id.int: row.seat_round_no for row in rows}[5] == 2


def test_br151_a_replacement_who_loses_again_and_comes_in_again() -> None:
    semifinals = [
        match(2, 1, (1, 2), (5, 10), W1, replacements=[came_in(5, 3)]),
        match(2, 2, (9, 11), (4, 12), W1),
    ]
    state = state_of([*QUARTERFINALS, *semifinals], third_place_match=False)
    assert as_ints(plan(state, disabled=[1, 3, 4])) == ([(5, 1)], [])
    final = [match(3, 1, (2, 5), (9, 11), W1, replacements=[came_in(5, 1)])]

    rows = places(
        state_of([*QUARTERFINALS, *semifinals, *final], third_place_match=False)
    )

    assert place_of(rows)[5] == 1
    assert (place_of(rows)[1], partner_of(rows)[1], partner_of(rows)[10]) == (3, 10, 1)
    assert (place_of(rows)[3], partner_of(rows)[3]) == (5, 13)
    seat_round = {row.player_id.int: row.seat_round_no for row in rows}
    assert (seat_round[1], seat_round[3], seat_round[5]) == (2, 1, None)


def test_br151_two_replacements_who_were_partners_give_up_both_seats() -> None:
    quarterfinals = [
        match(1, 1, (1, 9), (5, 6), W1),
        match(1, 2, (2, 10), (13, 14), W1),
        match(1, 3, (3, 11), (7, 15), W1),
        match(1, 4, (4, 12), (8, 16), W1),
    ]
    assert as_ints(plan(state_of(quarterfinals), disabled=[3, 4])) == (
        [(5, 3), (6, 4)],
        [],
    )
    rest = [
        match(2, 1, (1, 5), (9, 10), W1, replacements=[came_in(5, 3)]),
        match(2, 2, (2, 6), (11, 12), W1, replacements=[came_in(6, 4)]),
        match(3, 1, (1, 5), (2, 6), W1),
    ]

    rows = places(state_of([*quarterfinals, *rest], third_place_match=False))

    assert (place_of(rows)[3], place_of(rows)[4]) == (5, 5)
    assert (partner_of(rows)[3], partner_of(rows)[4]) == (4, 3)
    assert len(remix_season_points(rows, DEFAULT_TABLE)) == 16


# Caller bugs in stored replacements (BR-148, BR-152, BR-153)


def semifinals_with(*replacements: Replacement) -> list[RemixMatch]:
    return [
        match(2, 1, (1, 6), (4, 10), replacements=replacements),
        match(2, 2, (2, 9), (11, 12)),
    ]


@pytest.mark.parametrize(
    ("matches", "message"),
    [
        pytest.param(
            [
                replace(QUARTERFINALS[0], replacements=(came_in(1, 2),)),
                *QUARTERFINALS[1:],
            ],
            "replacement in round 1",
            id="BR-152-round-1",
        ),
        pytest.param(
            [*QUARTERFINALS, *semifinals_with(came_in(7, 3))],
            "does not play in it",
            id="not-in-the-match",
        ),
        pytest.param(
            [*QUARTERFINALS, *semifinals_with(came_in(6, 13))],
            "not in its pool",
            id="replaced-player-outside-the-pool",
        ),
        pytest.param(
            [
                *QUARTERFINALS,
                match(2, 1, (1, 6), (4, 10), replacements=[came_in(6, 3)]),
                match(2, 2, (2, 9), (11, 3), replacements=[came_in(3, 12)]),
            ],
            "not knocked out",
            id="BR-153-still-in",
        ),
        pytest.param(
            [
                *QUARTERFINALS,
                match(2, 1, (1, 6), (4, 10), replacements=[came_in(6, 3)]),
                match(2, 2, (2, 99), (11, 12), replacements=[came_in(99, 9)]),
            ],
            "not knocked out",
            id="not-in-the-knockout",
        ),
        pytest.param(
            [
                *QUARTERFINALS,
                match(2, 1, (1, 6), (4, 10), replacements=[came_in(6, 3)]),
                match(2, 2, (2, 7), (11, 12), replacements=[came_in(7, 3)]),
            ],
            "given twice",
            id="replaced-twice",
        ),
        pytest.param(
            [
                *QUARTERFINALS,
                match(
                    2, 1, (1, 6), (4, 10), replacements=[came_in(6, 3), came_in(6, 9)]
                ),
                match(2, 2, (2, 7), (11, 12)),
            ],
            "given twice",
            id="coming-in-twice",
        ),
        pytest.param(
            [*QUARTERFINALS, *semifinals_with()],
            "not drawn from the players who went through",
            id="BR-156-unmarked-replacement",
        ),
    ],
)
def test_remix_state_refuses_bad_replacements(
    matches: list[RemixMatch], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        state_of(matches, third_place_match=False)


def test_br153_remix_state_refuses_a_replaced_player_coming_in_later() -> None:
    semifinals = [
        match(2, 1, (1, 6), (4, 10), W2, replacements=[came_in(6, 3)]),
        match(2, 2, (2, 9), (11, 12), W1),
    ]
    final = [match(3, 1, (4, 3), (2, 9), replacements=[came_in(3, 10)])]

    with pytest.raises(ValueError, match="not knocked out"):
        state_of([*QUARTERFINALS, *semifinals, *final], third_place_match=False)


def test_br148_remix_state_refuses_a_third_place_replacement_from_the_final_pool() -> (
    None
):
    final = [
        match(3, 1, (1, 6), (7, 9), replacements=[came_in(7, 4)]),
        match(3, 1, (2, 10), (11, 12), third=True),
    ]

    with pytest.raises(ValueError, match="not in its pool"):
        state_of([*QUARTERFINALS, *SEMIFINALS, *final])


def test_br148_remix_state_refuses_a_third_place_replacement_for_a_finalist() -> None:
    final = [
        match(3, 1, (1, 6), (2, 9)),
        match(3, 1, (4, 10), (11, 7), third=True, replacements=[came_in(7, 2)]),
    ]

    with pytest.raises(ValueError, match="not in its pool"):
        state_of([*QUARTERFINALS, *SEMIFINALS, *final])


def test_br144_remix_state_refuses_an_unmarked_third_place_replacement() -> None:
    final = [
        match(3, 1, (1, 6), (2, 9)),
        match(3, 1, (4, 10), (11, 7), third=True),
    ]

    with pytest.raises(ValueError, match="not between the semifinal losers"):
        state_of([*QUARTERFINALS, *SEMIFINALS, *final])


# Properties


@st.composite
def knockouts(draw: st.DrawFn) -> tuple[int, bool, list[bool], list[int], bytes]:
    pairs = draw(st.integers(min_value=2, max_value=16))
    third_place_match = pairs >= 4 and draw(st.booleans())
    flips = draw(st.lists(st.booleans(), min_size=40, max_size=40))
    leaving = draw(
        st.lists(st.integers(min_value=1, max_value=2 * pairs), max_size=2 * pairs)
    )
    rng_seed = draw(st.binary(min_size=16, max_size=16))
    return pairs, third_place_match, flips, leaving, rng_seed


def first_round(pairs: int) -> list[RemixMatch]:
    """Round 1 as `draw_bracket` lays it out; pair k is players 2k - 1 and 2k."""
    bracket = draw_bracket(
        [EntryId(UUID(int=k)) for k in range(1, pairs + 1)], third_place_match=False
    )

    def team(entry_id: EntryId | None) -> Pair | None:
        return None if entry_id is None else (2 * entry_id.int - 1, 2 * entry_id.int)

    return [
        match(1, stored.position, team(stored.side_1), team(stored.side_2))
        for stored in bracket.first_round
    ]


def decide(matches: Iterable[RemixMatch], flips: Iterator[bool]) -> list[RemixMatch]:
    return [
        m
        if m.has_bye or m.outcome is not None
        else replace(m, outcome=W2 if next(flips, False) else W1)
        for m in matches
    ]


@settings(deadline=None)
@given(knockouts())
def test_br148_br151_players_leave_round_after_round_and_everybody_is_placed(
    case: tuple[int, bool, list[bool], list[int], bytes],
) -> None:
    pairs, third_place_match, flips, leaving, rng_seed = case
    players = range(1, 2 * pairs + 1)
    flip, leave = iter(flips), iter(leaving)
    disabled: set[int] = set()
    matches = decide(first_round(pairs), flip)
    while (
        state := state_of(matches, third_place_match=third_place_match)
    ).can_draw_next:
        disabled.add(next(leave, 0))
        drawn = draw_next_round(
            state,
            rng_seed=rng_seed,
            disabled=[pid(n) for n in disabled],
            standing=standing(players),
        )
        matches += decide(drawn, flip)

    state = state_of(matches, third_place_match=third_place_match)
    rows = places(state, players)

    assert sorted(r.player_id.int for r in rows) == list(players)
    counts = Counter(r.place for r in rows)
    expected = [2 for _ in state.newest_round for _ in range(2)]
    for round_ in reversed(state.rounds[: -2 if third_place_match else -1]):
        played = sum(not m.has_bye for m in round_)
        if played:
            expected.append(2 * played)
    assert [counts[p] for p in sorted(counts)] == expected
    assert len(remix_season_points(rows, DEFAULT_TABLE)) == len(rows)
