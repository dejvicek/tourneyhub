from collections.abc import Iterable
from dataclasses import replace
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
from tourneyhub.engine.tournaments import MatchFormat, Outcome

S1, S2, DRAW = Outcome.SIDE_1, Outcome.SIDE_2, Outcome.DRAW
A, B, C, D = (EntryId(UUID(int=n)) for n in (4, 3, 2, 1))  # ids against seed order


def rank(
    entries: Iterable[EntryId],
    *,
    matches: Iterable[PlayedMatch],
    sit_outs: Iterable[EntryId] = (),
    match_format: MatchFormat = MatchFormat.BO1,
) -> tuple[StandingRow, ...]:
    return round_robin_standings(
        entries, matches=matches, sit_outs=sit_outs, match_format=match_format
    )


def won(winner: EntryId, loser: EntryId, *scores: tuple[int, int]) -> PlayedMatch:
    """A BO1 win of `winner` on side 1, or a win in one game per score."""
    games = (S1,) * max(len(scores), 1)
    return PlayedMatch(
        side_1=winner, side_2=loser, outcome=S1, games=games, scores=scores
    )


def drew(side_1: EntryId, side_2: EntryId) -> PlayedMatch:
    return PlayedMatch(side_1=side_1, side_2=side_2, outcome=DRAW, games=(DRAW,))


def series(winner: EntryId, loser: EntryId, *games: Outcome) -> PlayedMatch:
    """A BO2, BO3 or BO5 match with these game winners, side 1 the winner."""
    outcome = S1 if games.count(S1) > games.count(S2) else DRAW
    return PlayedMatch(side_1=winner, side_2=loser, outcome=outcome, games=games)


def walkover(winner: EntryId, loser: EntryId) -> PlayedMatch:
    return PlayedMatch(side_1=winner, side_2=loser, outcome=S1, is_walkover=True)


def by_entry(rows: tuple[StandingRow, ...]) -> dict[EntryId, StandingRow]:
    return {row.entry_id: row for row in rows}


def test_br070_a_win_is_two_points_a_draw_one_and_a_loss_none() -> None:
    rows = by_entry(
        rank([A, B, C], matches=[won(A, B), drew(A, C), won(C, B, (10, 7))])
    )

    assert (rows[A].points, rows[A].won, rows[A].drawn, rows[A].lost) == (3, 1, 1, 0)
    assert (rows[C].points, rows[C].played, rows[C].score_difference) == (3, 2, 3)
    assert (rows[B].points, rows[B].lost, rows[B].score_difference) == (0, 2, -3)


def test_br093_a_walkover_side_2_win_counts_as_a_normal_win() -> None:
    match = PlayedMatch(side_1=A, side_2=B, outcome=S2, is_walkover=True)

    rows = by_entry(rank([A, B], matches=[match]))

    assert (rows[B].won, rows[B].points, rows[A].lost) == (1, 2, 1)
    assert (rows[B].game_difference, rows[A].game_difference) == (1, -1)


@pytest.mark.parametrize(
    ("match_format", "games"),
    [
        (MatchFormat.BO1, 1),
        (MatchFormat.BO2, 2),
        (MatchFormat.BO3, 2),
        (MatchFormat.BO5, 3),
    ],
)
def test_br101_a_walkover_counts_the_games_needed_to_win(
    match_format: MatchFormat, games: int
) -> None:
    rows = by_entry(rank([A, B], matches=[walkover(A, B)], match_format=match_format))

    assert (rows[A].game_difference, rows[B].game_difference) == (games, -games)


def test_br101_game_difference_counts_games_and_a_drawn_game_as_neither() -> None:
    rows = by_entry(
        rank(
            [A, B, C],
            matches=[series(A, B, S1, S2, S1), drew(A, C), series(C, B, S1, S1)],
            match_format=MatchFormat.BO3,
        )
    )

    assert [rows[e].game_difference for e in (A, B, C)] == [1, -3, 2]


def test_br101_game_difference_comes_before_score_difference_in_bo3() -> None:
    # B and C both beat D; B 2:0, C 2:1 with more goals. Level on points,
    # they did not meet, so the games decide before the goals.
    rows = rank(
        [C, B, D],
        matches=[
            PlayedMatch(
                side_1=B, side_2=D, outcome=S1, games=(S1, S1), scores=((5, 4), (5, 4))
            ),
            PlayedMatch(
                side_1=C,
                side_2=D,
                outcome=S1,
                games=(S1, S2, S1),
                scores=((10, 0), (0, 1), (10, 0)),
            ),
        ],
        match_format=MatchFormat.BO3,
    )

    assert [row.entry_id for row in rows] == [B, C, D]
    assert rows[0].ahead_by is RoundRobinTiebreaker.GAME_DIFFERENCE


def test_br101_game_difference_separates_bo1_entries_while_the_phase_runs() -> None:
    # Issue #61: A has played once and won; B twice, won once and lost once.
    # Both have 2 points, and game difference puts A first (+1 against 0).
    e = EntryId(UUID(int=5))
    rows = rank(
        [B, A, C, D, e],
        matches=[won(A, C), won(B, D), won(e, B), won(e, C)],
    )

    assert [(row.entry_id, row.points) for row in rows][:3] == [(e, 4), (A, 2), (B, 2)]
    assert (rows[1].game_difference, rows[2].game_difference) == (1, 0)
    assert rows[1].ahead_by is RoundRobinTiebreaker.GAME_DIFFERENCE
    assert rows[1].place < rows[2].place


def test_br071_a_sit_out_is_counted_but_earns_no_points_in_a_round_robin() -> None:
    rows = by_entry(rank([A, B, C], matches=[won(A, B)], sit_outs=[C]))

    assert (rows[C].sat_out, rows[C].points, rows[C].played) == (1, 0, 0)


def test_br071_sit_outs_do_not_decide_a_round_robin_with_a_late_entry() -> None:
    # BR-054: five entries start, a sixth joins after round 3. The five have
    # sat out three times each, the late one never; the points of their matches
    # alone decide, so the sit-outs do not lift anyone.
    late = EntryId(UUID(int=9))
    five = [A, B, C, D, EntryId(UUID(int=5))]
    matches = [won(A, B), won(C, D), won(late, five[4])]
    without = rank([*five, late], matches=matches)
    with_sit_outs = rank([*five, late], matches=matches, sit_outs=[*five, *five, *five])

    assert [(row.entry_id, row.points, row.place) for row in with_sit_outs] == [
        (row.entry_id, row.points, row.place) for row in without
    ]
    sat_out = {row.entry_id: row.sat_out for row in with_sit_outs}
    assert [sat_out[entry] for entry in five] == [3, 3, 3, 3, 3]
    assert sat_out[late] == 0


def test_br101_three_level_on_points_go_by_score_difference() -> None:
    # Everyone won once: three are level, so their matches do not decide.
    rows = rank(
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
    rows = rank(
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
    rows = rank([B, A], matches=[won(B, A, (10, 9)), won(A, B, (10, 2))])

    assert [row.entry_id for row in rows] == [A, B]
    assert rows[0].ahead_by is RoundRobinTiebreaker.SCORE_DIFFERENCE


def test_br074_entries_still_level_share_the_place_in_seed_order() -> None:
    rows = rank([A, B, C, D], matches=[won(C, D, (10, 5))])

    assert [(row.entry_id, row.place) for row in rows] == [
        (C, 1),
        (A, 2),
        (B, 2),
        (D, 4),
    ]
    assert [row.ahead_by for row in rows] == [
        None,
        None,
        RoundRobinTiebreaker.GAME_DIFFERENCE,
        None,
    ]


def test_br104_shared_places_become_tie_groups_for_the_places() -> None:
    rows = rank([A, B, C, D], matches=[won(C, D, (10, 5))])

    groups = standing_of(rows)
    places = place_entries(
        [PlacingEntry(entry_id=e, player_ids=()) for e in (A, B, C, D)],
        standing=groups,
    )

    assert groups == ((C,), (A, B), (D,))
    assert [(p.entry_id, p.place) for p in places] == [(C, 1), (B, 2), (A, 2), (D, 4)]


def test_fr060_the_form_lists_the_latest_five_results_oldest_first() -> None:
    matches = [won(A, B), drew(A, B), won(B, A), won(A, B), won(A, B), won(B, A)]

    rows = by_entry(rank([A, B], matches=matches))

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
        pytest.param(
            [A, B],
            [PlayedMatch(side_1=A, side_2=B, outcome=DRAW, is_walkover=True)],
            [],
            id="drawn-walkover",
        ),
    ],
)
def test_a_caller_bug_is_a_value_error(
    entries: list[EntryId], matches: list[PlayedMatch], sit_outs: list[EntryId]
) -> None:
    with pytest.raises(ValueError, match=r"twice|not among|both sides|is a draw"):
        rank(entries, matches=matches, sit_outs=sit_outs)


ENTRIES = [EntryId(UUID(int=n)) for n in range(1, 7)]


@st.composite
def results(draw: st.DrawFn) -> list[PlayedMatch]:
    pairs = [(a, b) for i, a in enumerate(ENTRIES) for b in ENTRIES[i + 1 :]]
    played = draw(st.lists(st.sampled_from(pairs), unique=True))
    matches = []
    for a, b in played:
        outcome = draw(st.sampled_from(list(Outcome)))
        is_walkover = outcome is not DRAW and draw(st.booleans())
        matches.append(
            PlayedMatch(
                side_1=a,
                side_2=b,
                outcome=outcome,
                games=()
                if is_walkover
                else draw(
                    st.lists(st.sampled_from(list(Outcome)), max_size=5).map(tuple)
                ),
                is_walkover=is_walkover,
                scores=draw(
                    st.lists(
                        st.tuples(st.integers(0, 10), st.integers(0, 10)), max_size=3
                    ).map(tuple)
                ),
            )
        )
    return matches


@given(results())
def test_br101_the_standings_are_ordered_and_balanced(
    matches: list[PlayedMatch],
) -> None:
    rows = rank(ENTRIES, matches=matches)

    assert sorted(row.entry_id for row in rows) == sorted(ENTRIES)
    assert [row.points for row in rows] == sorted(
        (row.points for row in rows), reverse=True
    )
    assert sum(row.won for row in rows) == sum(row.lost for row in rows)
    assert sum(row.game_difference for row in rows) == 0
    assert sum(row.score_difference for row in rows) == 0
    for index, row in enumerate(rows):
        assert row.place in {index + 1, rows[index - 1].place}


@given(results())
def test_br101_head_to_head_decides_exactly_two_entries_level_on_points(
    matches: list[PlayedMatch],
) -> None:
    rows = rank(ENTRIES, matches=matches)

    decided = set()
    for points in {row.points for row in rows}:
        level = [row for row in rows if row.points == points]
        if len(level) != 2:
            continue
        ids = {row.entry_id for row in level}
        meeting = next((m for m in matches if {m.side_1, m.side_2} == ids), None)
        if meeting is None or meeting.outcome is Outcome.DRAW:
            continue
        winner, loser = (
            (meeting.side_1, meeting.side_2)
            if meeting.outcome is S1
            else (meeting.side_2, meeting.side_1)
        )
        decided.add(winner)
        winner_row = next(row for row in level if row.entry_id == winner)
        loser_row = next(row for row in level if row.entry_id == loser)
        assert winner_row.place < loser_row.place
        assert rows.index(winner_row) + 1 == rows.index(loser_row)

    head_to_head = {
        row.entry_id
        for row in rows
        if row.ahead_by is RoundRobinTiebreaker.HEAD_TO_HEAD
    }
    assert head_to_head == decided


@given(
    results().flatmap(
        lambda played: st.tuples(st.just(played), st.permutations(played))
    )
)
def test_br101_the_ranking_does_not_depend_on_the_order_the_matches_arrive(
    played_and_shuffled: tuple[list[PlayedMatch], list[PlayedMatch]],
) -> None:
    played, shuffled = played_and_shuffled

    in_order = rank(ENTRIES, matches=played)
    other_order = rank(ENTRIES, matches=shuffled)

    assert [replace(row, form=()) for row in other_order] == [
        replace(row, form=()) for row in in_order
    ]
