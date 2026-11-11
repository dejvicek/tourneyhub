from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.ids import EntryId
from tourneyhub.engine.places import PlacingEntry, place_entries
from tourneyhub.engine.standings import (
    FORM_LENGTH,
    FormResult,
    PlayedMatch,
    RoundRobinTiebreaker,
    StandingRow,
    round_robin_standings,
    standing_of,
)
from tourneyhub.engine.tournaments import Outcome

S1, S2, DRAW = Outcome.SIDE_1, Outcome.SIDE_2, Outcome.DRAW
A, B, C, D = (EntryId(UUID(int=n)) for n in (4, 3, 2, 1))  # ids against seed order


def won(winner: EntryId, loser: EntryId, *scores: tuple[int, int]) -> PlayedMatch:
    return PlayedMatch(side_1=winner, side_2=loser, outcome=S1, scores=scores)


def drew(side_1: EntryId, side_2: EntryId) -> PlayedMatch:
    return PlayedMatch(side_1=side_1, side_2=side_2, outcome=DRAW)


def by_entry(rows: tuple[StandingRow, ...]) -> dict[EntryId, StandingRow]:
    return {row.entry_id: row for row in rows}


def test_br070_a_win_is_two_points_a_draw_one_and_a_loss_none() -> None:
    rows = by_entry(
        round_robin_standings(
            [A, B, C], matches=[won(A, B), drew(A, C), won(C, B, (10, 7))]
        )
    )

    assert (rows[A].points, rows[A].won, rows[A].drawn, rows[A].lost) == (3, 1, 1, 0)
    assert (rows[C].points, rows[C].played, rows[C].score_difference) == (3, 2, 3)
    assert (rows[B].points, rows[B].lost, rows[B].score_difference) == (0, 2, -3)


def test_br093_a_walkover_side_2_win_counts_as_a_normal_win() -> None:
    match = PlayedMatch(side_1=A, side_2=B, outcome=S2)

    rows = by_entry(round_robin_standings([A, B], matches=[match]))

    assert (rows[B].won, rows[B].points, rows[A].lost) == (1, 2, 1)


@pytest.mark.parametrize("sit_out_points", [0, 1])
def test_br071_a_sit_out_is_worth_the_settings_points(sit_out_points: int) -> None:
    rows = by_entry(
        round_robin_standings(
            [A, B, C],
            matches=[won(A, B)],
            sit_outs=[C],
            sit_out_points=sit_out_points,
        )
    )

    assert (rows[C].sat_out, rows[C].points, rows[C].played) == (1, sit_out_points, 0)


def test_br101_three_level_on_points_go_by_score_difference() -> None:
    # Everyone won once: three are level, so their matches do not decide.
    rows = round_robin_standings(
        [C, B, A],
        matches=[won(B, A, (10, 9)), won(A, C, (10, 0)), won(C, B, (10, 8))],
    )

    assert [(row.entry_id, row.score_difference) for row in rows] == [
        (A, 9),
        (B, -1),
        (C, -8),
    ]
    assert [row.place for row in rows] == [1, 2, 3]
    assert [row.ahead_by for row in rows] == [
        RoundRobinTiebreaker.SCORE_DIFFERENCE,
        RoundRobinTiebreaker.SCORE_DIFFERENCE,
        None,
    ]


def test_br101_head_to_head_puts_the_winner_of_their_match_first() -> None:
    # A and B both have 2 points; A has the better score difference but B won.
    rows = round_robin_standings(
        [A, B, C],
        matches=[won(B, A, (10, 9)), won(A, C, (10, 0))],
        sit_outs=[C],
    )

    assert [row.entry_id for row in rows] == [B, A, C]
    assert [row.place for row in rows] == [1, 2, 3]
    assert rows[0].ahead_by is RoundRobinTiebreaker.HEAD_TO_HEAD
    assert rows[1].ahead_by is None


def test_br101_a_level_head_to_head_falls_back_to_score_difference() -> None:
    # Two legs: A and B beat each other once; A won by more.
    rows = round_robin_standings(
        [B, A], matches=[won(B, A, (10, 9)), won(A, B, (10, 2))]
    )

    assert [row.entry_id for row in rows] == [A, B]
    assert rows[0].ahead_by is RoundRobinTiebreaker.SCORE_DIFFERENCE


def test_br074_entries_still_level_share_the_place_in_seed_order() -> None:
    rows = round_robin_standings([A, B, C, D], matches=[won(C, D, (10, 5))])

    assert [(row.entry_id, row.place) for row in rows] == [
        (C, 1),
        (A, 2),
        (B, 2),
        (D, 4),
    ]
    assert [row.ahead_by for row in rows] == [
        None,
        None,
        RoundRobinTiebreaker.SCORE_DIFFERENCE,
        None,
    ]


def test_br104_shared_places_become_tie_groups_for_the_places() -> None:
    rows = round_robin_standings([A, B, C, D], matches=[won(C, D, (10, 5))])

    groups = standing_of(rows)
    places = place_entries(
        [PlacingEntry(entry_id=e, player_ids=()) for e in (A, B, C, D)],
        standing=groups,
    )

    assert groups == ((C,), (A, B), (D,))
    assert [(p.entry_id, p.place) for p in places] == [(C, 1), (B, 2), (A, 2), (D, 4)]


def test_fr060_the_form_lists_the_latest_five_results_oldest_first() -> None:
    matches = [won(A, B), drew(A, B), won(B, A), won(A, B), won(A, B), won(B, A)]

    rows = by_entry(round_robin_standings([A, B], matches=matches))

    assert len(rows[A].form) == FORM_LENGTH
    assert rows[A].form == (
        FormResult.DRAWN,
        FormResult.LOST,
        FormResult.WON,
        FormResult.WON,
        FormResult.LOST,
    )


@pytest.mark.parametrize(
    ("entries", "matches", "sit_outs"),
    [
        pytest.param([A, A], [], [], id="entry-twice"),
        pytest.param([A, B], [won(A, C)], [], id="unknown-in-match"),
        pytest.param([A, B], [], [C], id="unknown-sit-out"),
        pytest.param([A, B], [won(A, A)], [], id="both-sides"),
    ],
)
def test_a_caller_bug_is_a_value_error(
    entries: list[EntryId], matches: list[PlayedMatch], sit_outs: list[EntryId]
) -> None:
    with pytest.raises(ValueError, match=r"twice|not among|both sides"):
        round_robin_standings(entries, matches=matches, sit_outs=sit_outs)


ENTRIES = [EntryId(UUID(int=n)) for n in range(1, 7)]


@st.composite
def results(draw: st.DrawFn) -> list[PlayedMatch]:
    pairs = [(a, b) for i, a in enumerate(ENTRIES) for b in ENTRIES[i + 1 :]]
    played = draw(st.lists(st.sampled_from(pairs), unique=True))
    return [
        PlayedMatch(
            side_1=a,
            side_2=b,
            outcome=draw(st.sampled_from(list(Outcome))),
            scores=draw(
                st.lists(
                    st.tuples(st.integers(0, 10), st.integers(0, 10)), max_size=3
                ).map(tuple)
            ),
        )
        for a, b in played
    ]


@given(results())
def test_br101_the_standings_are_ordered_and_balanced(
    matches: list[PlayedMatch],
) -> None:
    rows = round_robin_standings(ENTRIES, matches=matches)

    assert sorted(row.entry_id for row in rows) == sorted(ENTRIES)
    assert [row.points for row in rows] == sorted(
        (row.points for row in rows), reverse=True
    )
    assert sum(row.won for row in rows) == sum(row.lost for row in rows)
    assert sum(row.score_difference for row in rows) == 0
    for index, row in enumerate(rows):
        assert row.place in {index + 1, rows[index - 1].place}
