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
    THIRD_PLACE_PURPOSE,
    RemixMatch,
    RemixPlace,
    RemixState,
    allows_result,
    draw_next_round,
    place_remix_players,
    players_who_left,
    remix_purpose,
    remix_season_points,
    remix_state,
)
from tourneyhub.engine.tournaments import Outcome

SEED = bytes(range(16))
DEFAULT_TABLE = [10, 8, 6, 4, 2]  # FR-011

type Pair = tuple[int, int]


def pid(n: int) -> PlayerId:
    return PlayerId(UUID(int=n))


def eid(n: int) -> EntryId:
    return EntryId(UUID(int=1000 + n))


def key(round_no: int, position: int, *, third: bool = False) -> MatchKey:
    return MatchKey(round_no=round_no, is_third_place=third, position=position)


def match(
    round_no: int,
    position: int,
    side_1: Pair | None,
    side_2: Pair | None,
    outcome: Outcome | None = None,
    *,
    third: bool = False,
) -> RemixMatch:
    return RemixMatch(
        key=key(round_no, position, third=third),
        side_1=None if side_1 is None else (pid(side_1[0]), pid(side_1[1])),
        side_2=None if side_2 is None else (pid(side_2[0]), pid(side_2[1])),
        outcome=outcome,
    )


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
    """Give every played match without a result one; side 2 wins on a flip."""
    return [
        m
        if m.has_bye or m.outcome is not None
        else replace(
            m, outcome=Outcome.SIDE_2 if next(flips, False) else Outcome.SIDE_1
        )
        for m in matches
    ]


def play_out(
    pairs: int,
    *,
    third_place_match: bool,
    flips: Iterable[bool] = (),
    rng_seed: bytes = SEED,
) -> list[RemixMatch]:
    """Draw and decide round after round until no round can be drawn."""
    flip = iter(flips)
    matches = decide(first_round(pairs), flip)
    while (
        state := remix_state(matches, third_place_match=third_place_match)
    ).can_draw_next:
        matches += decide(draw_next_round(state, rng_seed=rng_seed), flip)
    return matches


def teams(matches: Iterable[RemixMatch]) -> set[frozenset[int]]:
    return {
        frozenset(player_id.int for player_id in side)
        for m in matches
        for side in (m.side_1, m.side_2)
        if side is not None
    }


def ints(players: Iterable[PlayerId]) -> set[int]:
    return {player_id.int for player_id in players}


def entries_for(players: Iterable[int]) -> list[PlacingEntry]:
    return [
        PlacingEntry(entry_id=eid(n), player_ids=(pid(n),), seed=n) for n in players
    ]


def standing_of(players: Iterable[int]) -> list[list[EntryId]]:
    """A standing with player n alone at place n."""
    return [[eid(n)] for n in players]


def places_of(rows: Iterable[RemixPlace]) -> dict[int, int]:
    return {row.player_id.int: row.place for row in rows}


# Four pairs: 1+2 beat 3+4, 7+8 beat 5+6.
FOUR_PAIRS_ROUND_1 = [
    match(1, 1, (1, 2), (3, 4), Outcome.SIDE_1),
    match(1, 2, (5, 6), (7, 8), Outcome.SIDE_2),
]


# Lots and the draw (BR-141 to BR-144, BR-146, BR-156)


def test_br156_the_lots_have_their_own_purposes() -> None:
    assert remix_purpose(2) == "lord_have_mercy:round-2"
    assert remix_purpose(5) == "lord_have_mercy:round-5"
    assert THIRD_PLACE_PURPOSE == "lord_have_mercy:third-place"


def test_br156_round_1_has_no_re_mix_purpose() -> None:
    with pytest.raises(ValueError, match="not a re-mixed round"):
        remix_purpose(1)


def test_br156_the_order_of_the_stored_matches_does_not_change_the_draw() -> None:
    matches = decide(first_round(8), iter([True, False, True]))

    forward = draw_next_round(
        remix_state(matches, third_place_match=False), rng_seed=SEED
    )
    backward = draw_next_round(
        remix_state(matches[::-1], third_place_match=False), rng_seed=SEED
    )

    assert forward == backward


def test_br156_the_same_players_give_the_same_pairs_and_matches() -> None:
    other_round_1 = [
        match(1, 1, (1, 2), (5, 6), Outcome.SIDE_1),
        match(1, 2, (3, 4), (7, 8), Outcome.SIDE_2),
    ]

    drawn = draw_next_round(
        remix_state(FOUR_PAIRS_ROUND_1, third_place_match=False), rng_seed=SEED
    )
    again = draw_next_round(
        remix_state(other_round_1, third_place_match=False), rng_seed=SEED
    )

    assert drawn == again


def test_br146_deleting_the_newest_round_and_drawing_again_gives_the_same_round() -> (
    None
):
    matches = play_out(8, third_place_match=True, flips=[True, False] * 10)
    before_final = [m for m in matches if m.key.round_no <= 2]
    final_round = [replace(m, outcome=None) for m in matches if m.key.round_no == 3]

    drawn_again = draw_next_round(
        remix_state(before_final, third_place_match=True), rng_seed=SEED
    )

    assert list(drawn_again) == final_round


def test_br141_the_next_round_is_drawn_from_the_winners_in_lot_order() -> None:
    round_1 = decide(first_round(8), iter([False, True] * 4))
    winners = {p for m in round_1 for p in ints(m.winner or ())}

    drawn = draw_next_round(
        remix_state(round_1, third_place_match=False), rng_seed=SEED
    )

    lot = order_by_lot(
        sorted(map(pid, winners)), rng_seed=SEED, purpose=remix_purpose(2)
    )
    assert [k.int for m in drawn for k in m.players] == [p.int for p in lot]
    assert [m.key for m in drawn] == [key(2, 1), key(2, 2)]
    assert all(m.outcome is None for m in drawn)


def test_br141_br143_the_pairs_are_mixed_again() -> None:
    round_1 = decide(first_round(8), iter(()))
    state = remix_state(round_1, third_place_match=False)

    drawn = draw_next_round(state, rng_seed=SEED)

    lot = order_by_lot(state.going_through, rng_seed=SEED, purpose=remix_purpose(2))
    pairs = [(lot[i], lot[i + 1]) for i in range(0, len(lot), 2)]
    expected = [
        RemixMatch(
            key=key(2, position),
            side_1=pairs[2 * position - 2],
            side_2=pairs[2 * position - 1],
            outcome=None,
        )
        for position in range(1, len(pairs) // 2 + 1)
    ]
    assert list(drawn) == expected
    assert teams(drawn) - teams(round_1)


def test_br141_pairs_with_a_bye_are_mixed_with_the_winners() -> None:
    round_1 = decide(first_round(6), iter(()))  # pairs 1 and 2 have byes
    state = remix_state(round_1, third_place_match=False)

    drawn = draw_next_round(state, rng_seed=bytes(16))  # a seed that mixes

    assert state.going_through == {pid(n) for n in range(1, 9)}
    assert ints(p for m in drawn for p in m.players) == set(range(1, 9))
    assert any(
        len(team & {1, 2, 3, 4}) == 1 for team in teams(drawn)
    )  # a bye pair's player with a winner


def test_br141_a_match_without_a_result_sends_nobody_through_yet() -> None:
    state = remix_state(
        [FOUR_PAIRS_ROUND_1[0], replace(FOUR_PAIRS_ROUND_1[1], outcome=None)],
        third_place_match=False,
    )

    assert ints(state.going_through) == {1, 2}


def test_br142_br144_the_final_and_the_third_place_match_are_drawn_together() -> None:
    state = remix_state(FOUR_PAIRS_ROUND_1, third_place_match=True)

    final, third_place = draw_next_round(state, rng_seed=SEED)

    finalists = order_by_lot(
        map(pid, (1, 2, 7, 8)), rng_seed=SEED, purpose=remix_purpose(2)
    )
    losers = order_by_lot(
        map(pid, (3, 4, 5, 6)), rng_seed=SEED, purpose=THIRD_PLACE_PURPOSE
    )
    assert final.key == key(2, 1)
    assert final.players == finalists
    assert third_place.key == key(2, 1, third=True)
    assert third_place.players == losers
    assert state.semifinal_losers == {pid(n) for n in (3, 4, 5, 6)}


def test_br156_the_final_and_the_third_place_match_have_their_own_lots() -> None:
    matches = play_out(8, third_place_match=True, flips=[True, False] * 10)
    state = remix_state(
        [m for m in matches if m.key.round_no <= 2], third_place_match=True
    )

    final, third_place = draw_next_round(state, rng_seed=SEED)

    finalists = order_by_lot(
        state.going_through, rng_seed=SEED, purpose=remix_purpose(3)
    )
    losers = order_by_lot(
        state.semifinal_losers, rng_seed=SEED, purpose=THIRD_PLACE_PURPOSE
    )
    assert final.key == key(3, 1)
    assert final.side_1 == (finalists[0], finalists[1])
    assert final.side_2 == (finalists[2], finalists[3])
    assert third_place.key == key(3, 1, third=True)
    assert third_place.side_1 == (losers[0], losers[1])
    assert third_place.side_2 == (losers[2], losers[3])
    assert ints(finalists).isdisjoint(ints(losers))


def test_br144_a_knockout_of_2_pairs_has_no_semifinal_losers() -> None:
    state = remix_state([match(1, 1, (1, 2), (3, 4))], third_place_match=False)

    assert state.semifinal_losers == frozenset()
    assert state.round_count == 1


# BR-140, FR-037


def test_br140_no_draw_while_a_match_of_the_newest_round_has_no_result() -> None:
    state = remix_state(
        [FOUR_PAIRS_ROUND_1[0], replace(FOUR_PAIRS_ROUND_1[1], outcome=None)],
        third_place_match=False,
    )

    assert not state.can_draw_next
    with pytest.raises(ValueError, match="cannot be drawn"):
        draw_next_round(state, rng_seed=SEED)


def test_br140_no_draw_after_the_final() -> None:
    state = remix_state(play_out(4, third_place_match=False), third_place_match=False)

    assert state.rounds_drawn == state.round_count == 2
    assert not state.can_draw_next


def test_br140_a_knockout_of_2_pairs_has_nothing_to_re_mix() -> None:
    state = remix_state(
        [match(1, 1, (1, 2), (3, 4), Outcome.SIDE_2)], third_place_match=False
    )

    assert not state.can_draw_next
    assert state.is_complete


def test_fr037_not_complete_after_round_1_although_every_match_has_a_result() -> None:
    state = remix_state(FOUR_PAIRS_ROUND_1, third_place_match=False)

    assert not state.is_complete


def test_fr037_complete_only_with_the_final_and_the_third_place_result() -> None:
    final, third_place = draw_next_round(
        remix_state(FOUR_PAIRS_ROUND_1, third_place_match=True), rng_seed=SEED
    )
    played_final = replace(final, outcome=Outcome.SIDE_1)

    waiting = remix_state(
        [*FOUR_PAIRS_ROUND_1, played_final, third_place], third_place_match=True
    )
    done = remix_state(
        [
            *FOUR_PAIRS_ROUND_1,
            played_final,
            replace(third_place, outcome=Outcome.SIDE_2),
        ],
        third_place_match=True,
    )

    assert not waiting.is_complete
    assert done.is_complete


# BR-146: the lock


def final_round_state() -> RemixState:
    final, third_place = draw_next_round(
        remix_state(FOUR_PAIRS_ROUND_1, third_place_match=True), rng_seed=SEED
    )
    return remix_state(
        [*FOUR_PAIRS_ROUND_1, replace(final, outcome=Outcome.SIDE_1), third_place],
        third_place_match=True,
    )


@pytest.mark.parametrize(
    ("match_key", "outcome"),
    [
        pytest.param(key(2, 1), Outcome.SIDE_2, id="BR-146-change-the-final-winner"),
        pytest.param(key(2, 1), None, id="BR-146-clear-the-final"),
        pytest.param(key(2, 1, third=True), Outcome.SIDE_1, id="BR-146-third-place"),
        pytest.param(key(2, 1, third=True), None, id="BR-146-third-place-clear"),
    ],
)
def test_br146_the_newest_round_takes_any_result(
    match_key: MatchKey, outcome: Outcome | None
) -> None:
    assert allows_result(final_round_state(), match_key, outcome)


def test_br146_a_locked_round_takes_a_correction_with_the_same_winner() -> None:
    assert allows_result(final_round_state(), key(1, 2), Outcome.SIDE_2)


@pytest.mark.parametrize(
    "outcome",
    [
        pytest.param(Outcome.SIDE_1, id="BR-146-other-winner"),
        pytest.param(None, id="BR-146-no-clear"),
    ],
)
def test_br146_a_locked_round_keeps_its_winner(outcome: Outcome | None) -> None:
    assert not allows_result(final_round_state(), key(1, 2), outcome)


def test_br146_an_unknown_match_is_a_caller_bug() -> None:
    with pytest.raises(ValueError, match="not drawn"):
        allows_result(final_round_state(), key(3, 1), Outcome.SIDE_1)


def test_br146_a_bye_takes_no_result() -> None:
    state = remix_state(first_round(6), third_place_match=False)

    with pytest.raises(ValueError, match="takes no result"):
        allows_result(state, key(1, 1), Outcome.SIDE_1)


def test_br043_a_result_is_never_a_draw() -> None:
    with pytest.raises(ValueError, match="cannot be a draw"):
        allows_result(final_round_state(), key(2, 1), Outcome.DRAW)


# BR-147, BR-149, BR-157: who is still in, who left


def test_br147_without_a_third_place_match_the_semifinal_losers_are_out() -> None:
    state = remix_state(FOUR_PAIRS_ROUND_1, third_place_match=False)

    assert ints(state.still_in) == {1, 2, 7, 8}


def test_br147_with_a_third_place_match_the_semifinal_losers_wait() -> None:
    state = remix_state(FOUR_PAIRS_ROUND_1, third_place_match=True)

    assert ints(state.still_in) == set(range(1, 9))


def test_br147_a_bye_or_a_match_without_a_result_keeps_its_players_in() -> None:
    round_1 = first_round(6)  # 1: 1+2 bye; 2: 7+8 v 9+10; 3: 3+4 bye; 4: 5+6 v 11+12
    round_1[1] = replace(round_1[1], outcome=Outcome.SIDE_1)

    state = remix_state(round_1, third_place_match=False)

    assert ints(state.still_in) == {1, 2, 3, 4, 5, 6, 7, 8, 11, 12}
    assert ints(state.players) == set(range(1, 13))


def test_br147_after_the_last_results_the_losers_are_out() -> None:
    state = final_round_state()
    final, third_place = state.newest_round
    done = remix_state(
        [*FOUR_PAIRS_ROUND_1, final, replace(third_place, outcome=Outcome.SIDE_1)],
        third_place_match=True,
    )

    assert state.still_in == {*final.players[:2], *third_place.players}
    assert done.still_in == {*final.players[:2], *third_place.players[:2]}


def test_br147_br149_a_disabled_player_still_in_has_left() -> None:
    state = remix_state(FOUR_PAIRS_ROUND_1, third_place_match=False)

    left = players_who_left(state, [pid(1), pid(3), pid(99)])

    assert left == {pid(1)}


def test_br157_both_pairs_of_a_match_can_have_a_player_who_left() -> None:
    state = final_round_state()
    final = state.newest_round[0]
    final_open = remix_state(
        [*FOUR_PAIRS_ROUND_1, replace(final, outcome=None), state.newest_round[1]],
        third_place_match=True,
    )
    disabled = [final.players[0], final.players[3]]  # one from each pair

    assert players_who_left(final_open, disabled) == set(disabled)


# BR-145, BR-103, BR-104, BR-111: places and points


def finished(*, third_place_match: bool) -> list[RemixMatch]:
    """Four pairs played out, side 1 winning every later match."""
    matches = list(FOUR_PAIRS_ROUND_1)
    drawn = draw_next_round(
        remix_state(matches, third_place_match=third_place_match), rng_seed=SEED
    )
    return [*matches, *(replace(m, outcome=Outcome.SIDE_1) for m in drawn)]


def test_br145_four_pairs_with_a_third_place_match() -> None:
    matches = finished(third_place_match=True)
    final, third_place = matches[2], matches[3]
    state = remix_state(matches, third_place_match=True)

    rows = place_remix_players(
        state, entries=entries_for(range(1, 11)), standing=standing_of(range(1, 11))
    )

    expected = {
        **dict.fromkeys(ints(final.side_1 or ()), 1),
        **dict.fromkeys(ints(final.side_2 or ()), 2),
        **dict.fromkeys(ints(third_place.side_1 or ()), 3),
        **dict.fromkeys(ints(third_place.side_2 or ()), 4),
        9: 5,
        10: 6,
    }
    assert places_of(rows) == expected
    points = {
        row.player_id.int: row.points
        for row in remix_season_points(rows, DEFAULT_TABLE)
    }
    assert points == {
        p: [10, 8, 6, 4, 2, 0][place - 1] for p, place in expected.items()
    }


def test_br145_br111_without_a_third_place_match_the_semifinal_losers_share_3rd() -> (
    None
):
    matches = finished(third_place_match=False)
    final = matches[2]
    state = remix_state(matches, third_place_match=False)

    rows = place_remix_players(
        state, entries=entries_for(range(1, 10)), standing=standing_of(range(1, 10))
    )
    points = {
        row.player_id.int: row.points
        for row in remix_season_points(rows, DEFAULT_TABLE)
    }

    winners, losers = ints(final.side_1 or ()), ints(final.side_2 or ())
    assert places_of(rows) == {
        **dict.fromkeys(winners, 1),
        **dict.fromkeys(losers, 2),
        **dict.fromkeys((3, 4, 5, 6), 3),
        9: 5,
    }
    assert points == {
        **dict.fromkeys(winners, 10),
        **dict.fromkeys(losers, 8),
        **dict.fromkeys((3, 4, 5, 6), 5),
        9: 2,
    }


def test_br145_a_player_takes_the_partner_of_their_last_match() -> None:
    matches = finished(third_place_match=True)
    final = matches[2]
    state = remix_state(matches, third_place_match=True)

    rows = place_remix_players(state, entries=entries_for(range(1, 9)))

    first, second = final.players[:2]
    partners = {row.player_id: row.partner_id for row in rows}
    assert partners[first] == second
    assert partners[second] == first


def test_br145_br111_eight_pairs_losing_the_quarterfinals_share_5th() -> None:
    matches = play_out(8, third_place_match=True)
    state = remix_state(matches, third_place_match=True)
    quarterfinal_losers = ints(
        p for m in matches if m.key.round_no == 1 for p in m.loser or ()
    )

    rows = place_remix_players(
        state, entries=entries_for(range(1, 18)), standing=standing_of(range(1, 18))
    )
    points = {
        row.player_id.int: row.points
        for row in remix_season_points(rows, DEFAULT_TABLE)
    }

    assert Counter(places_of(rows).values()) == {1: 2, 2: 2, 3: 2, 4: 2, 5: 8, 9: 1}
    assert {places_of(rows)[p] for p in quarterfinal_losers} == {5}
    assert {points[p] for p in quarterfinal_losers} == {0}
    assert places_of(rows)[17] == 9


def test_br145_a_pair_that_had_a_bye_is_placed_by_its_last_match() -> None:
    matches = play_out(6, third_place_match=True)
    state = remix_state(matches, third_place_match=True)

    rows = place_remix_players(state, entries=entries_for(range(1, 13)))

    by_player = places_of(rows)
    assert Counter(by_player.values()) == {1: 2, 2: 2, 3: 2, 4: 2, 5: 4}
    assert by_player[1] in {1, 2, 3, 4}  # pair 1 had a bye in round 1


def test_br103_br145_after_byes_the_best_non_qualifier_follows_the_pairs() -> None:
    matches = play_out(6, third_place_match=True)
    state = remix_state(matches, third_place_match=True)

    rows = place_remix_players(
        state, entries=entries_for(range(1, 14)), standing=standing_of(range(1, 14))
    )
    points = {
        row.player_id.int: row.points
        for row in remix_season_points(rows, DEFAULT_TABLE)
    }

    # 6 pairs: 1st, 2nd, 3rd, 4th, two round-1 losing pairs share 5th.
    assert places_of(rows)[13] == 7
    assert points[13] == 0


def test_br104_shared_places_list_pairs_by_match_and_players_by_standing() -> None:
    matches = play_out(8, third_place_match=False)
    state = remix_state(matches, third_place_match=False)
    quarterfinals = [m for m in matches if m.key.round_no == 1]
    reversed_standing = standing_of(range(16, 0, -1))

    rows = place_remix_players(
        state, entries=entries_for(range(1, 17)), standing=reversed_standing
    )

    fifth = [row.player_id.int for row in rows if row.place == 5]
    expected = [
        p for m in quarterfinals for p in sorted(ints(m.loser or ()), reverse=True)
    ]
    assert fifth == expected


def test_br104_non_qualifiers_sharing_a_place_by_seed_seedless_last() -> None:
    matches = play_out(2, third_place_match=False)
    state = remix_state(matches, third_place_match=False)
    entries = [
        *entries_for(range(1, 5)),
        PlacingEntry(entry_id=eid(5), player_ids=(pid(5),)),
        PlacingEntry(entry_id=eid(6), player_ids=(pid(6),), seed=7),
        PlacingEntry(entry_id=eid(7), player_ids=(pid(7),), seed=6),
    ]

    rows = place_remix_players(
        state, entries=entries, standing=[[eid(5), eid(6), eid(7)], [eid(1)]]
    )

    assert [(row.player_id.int, row.place) for row in rows[4:]] == [
        (7, 3),
        (6, 3),
        (5, 3),
    ]


def test_br145_a_knockout_of_2_pairs() -> None:
    state = remix_state(
        [match(1, 1, (1, 2), (3, 4), Outcome.SIDE_2)], third_place_match=False
    )

    rows = place_remix_players(
        state, entries=entries_for(range(1, 6)), standing=standing_of(range(1, 6))
    )

    assert places_of(rows) == {3: 1, 4: 1, 1: 2, 2: 2, 5: 3}


def test_br145_the_order_of_entries_and_standing_does_not_matter() -> None:
    state = remix_state(play_out(6, third_place_match=True), third_place_match=True)
    entries = entries_for(range(1, 16))
    standing = [[eid(n) for n in range(1, 13)], [eid(13), eid(14)], [eid(15)]]

    one = place_remix_players(state, entries=entries, standing=standing)
    two = place_remix_players(
        state,
        entries=entries[::-1],
        standing=[group[::-1] for group in standing],
    )

    assert one == two


# Caller bugs


def test_br040_remix_state_refuses_a_round_one_larger_than_its_pairs_need() -> None:
    round_1 = [match(1, k, (2 * k - 1, 2 * k), None) for k in range(1, 5)]

    with pytest.raises(ValueError, match="bracket"):
        remix_state(round_1, third_place_match=False)


def test_remix_state_refuses_a_match_given_twice() -> None:
    with pytest.raises(ValueError, match="matches given twice"):
        remix_state(
            [*FOUR_PAIRS_ROUND_1, FOUR_PAIRS_ROUND_1[0]], third_place_match=False
        )


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        pytest.param(match(1, 2, None, None), "two byes", id="two-byes"),
        pytest.param(
            match(1, 2, (5, 6), None, Outcome.SIDE_1),
            "bye and a result",
            id="bye-result",
        ),
        pytest.param(
            match(1, 2, (5, 6), (7, 8), Outcome.DRAW), "draw", id="BR-043-draw"
        ),
        pytest.param(
            match(1, 2, (5, 5), (7, 8)), "not two different players", id="one-player"
        ),
        pytest.param(match(1, 3, (5, 6), (7, 8)), "positions are not 1 to n", id="gap"),
    ],
)
def test_remix_state_refuses_a_bad_round_1(bad: RemixMatch, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        remix_state([FOUR_PAIRS_ROUND_1[0], bad], third_place_match=False)


def test_remix_state_refuses_a_bye_after_round_1() -> None:
    with pytest.raises(ValueError, match="bye after round 1"):
        remix_state(
            [*FOUR_PAIRS_ROUND_1, match(2, 1, (1, 2), None)], third_place_match=False
        )


def test_remix_state_refuses_a_bracket_that_is_not_a_power_of_two() -> None:
    round_1 = [*FOUR_PAIRS_ROUND_1, match(1, 3, (9, 10), (11, 12))]

    with pytest.raises(ValueError, match="power of two"):
        remix_state(round_1, third_place_match=False)


def test_br080_remix_state_refuses_a_single_pair() -> None:
    with pytest.raises(ValueError, match="too few"):
        remix_state([match(1, 1, (1, 2), None)], third_place_match=False)


def test_br080_a_third_place_match_needs_4_pairs() -> None:
    round_1 = [match(1, 1, (1, 2), (3, 4)), match(1, 2, (5, 6), None)]

    with pytest.raises(ValueError, match="too few"):
        remix_state(round_1, third_place_match=True)


def test_remix_state_refuses_no_matches() -> None:
    with pytest.raises(ValueError, match="power of two"):
        remix_state([], third_place_match=False)


@pytest.mark.parametrize(
    "later",
    [
        pytest.param([match(3, 1, (1, 2), (7, 8))], id="round-2-missing"),
        pytest.param(
            [match(2, 1, (1, 2), (7, 8)), match(3, 1, (1, 2), (7, 8))],
            id="beyond-the-final",
        ),
    ],
)
def test_remix_state_refuses_rounds_that_are_not_contiguous(
    later: list[RemixMatch],
) -> None:
    with pytest.raises(ValueError, match="are not 1 to at most"):
        remix_state([*FOUR_PAIRS_ROUND_1, *later], third_place_match=False)


def test_remix_state_refuses_a_round_with_the_wrong_number_of_matches() -> None:
    round_1 = decide(first_round(8), iter(()))

    with pytest.raises(ValueError, match="does not have its 2 matches"):
        remix_state([*round_1, match(2, 1, (1, 2), (5, 6))], third_place_match=False)


def test_remix_state_refuses_a_third_place_match_outside_the_final_round() -> None:
    state = remix_state(decide(first_round(8), iter(())), third_place_match=True)
    round_2 = draw_next_round(state, rng_seed=SEED)
    stray = match(2, 1, (90, 91), (92, 93), third=True)

    with pytest.raises(ValueError, match="not in the final's round"):
        remix_state([*state.matches, *round_2, stray], third_place_match=True)


def test_remix_state_refuses_a_third_place_match_at_another_position() -> None:
    final_round = final_round_state()
    final, third_place = final_round.newest_round
    moved = replace(third_place, key=key(2, 2, third=True))

    with pytest.raises(ValueError, match="not in the final's round"):
        remix_state([*FOUR_PAIRS_ROUND_1, final, moved], third_place_match=True)


def test_remix_state_refuses_a_second_third_place_match() -> None:
    final, third_place = final_round_state().newest_round
    extra = match(2, 2, (90, 91), (92, 93), third=True)

    with pytest.raises(ValueError, match="not in the final's round"):
        remix_state(
            [*FOUR_PAIRS_ROUND_1, final, third_place, extra], third_place_match=True
        )


def test_remix_state_refuses_a_player_twice_in_round_1() -> None:
    round_1 = [match(1, 1, (1, 2), (3, 4)), match(1, 2, (1, 6), (7, 8))]

    with pytest.raises(ValueError, match="is given twice"):
        remix_state(round_1, third_place_match=False)


def test_br144_a_player_cannot_play_the_final_and_the_third_place_match() -> None:
    final, _ = final_round_state().newest_round
    third_place = match(2, 1, (3, 4), (5, final.players[0].int), third=True)

    with pytest.raises(ValueError, match="is given twice"):
        remix_state([*FOUR_PAIRS_ROUND_1, final, third_place], third_place_match=True)


def test_br140_remix_state_refuses_a_round_drawn_too_early() -> None:
    round_1 = [FOUR_PAIRS_ROUND_1[0], replace(FOUR_PAIRS_ROUND_1[1], outcome=None)]

    with pytest.raises(ValueError, match="before round 1 is complete"):
        remix_state([*round_1, match(2, 1, (1, 7), (2, 8))], third_place_match=False)


def test_br141_remix_state_refuses_a_round_of_other_players() -> None:
    with pytest.raises(ValueError, match="not drawn from the players who went through"):
        remix_state(
            [*FOUR_PAIRS_ROUND_1, match(2, 1, (1, 3), (2, 8))], third_place_match=False
        )


def test_br144_remix_state_refuses_a_missing_third_place_match() -> None:
    final, _ = final_round_state().newest_round

    with pytest.raises(ValueError, match="does not match the knockout's setting"):
        remix_state([*FOUR_PAIRS_ROUND_1, final], third_place_match=True)


def test_br144_remix_state_refuses_a_third_place_match_against_the_flag() -> None:
    final, third_place = final_round_state().newest_round

    with pytest.raises(ValueError, match="does not match the knockout's setting"):
        remix_state([*FOUR_PAIRS_ROUND_1, final, third_place], third_place_match=False)


def test_br144_remix_state_refuses_a_third_place_match_of_other_players() -> None:
    final, _ = final_round_state().newest_round
    third_place = match(2, 1, (3, 4), (5, 99), third=True)

    with pytest.raises(ValueError, match="not between the semifinal losers"):
        remix_state([*FOUR_PAIRS_ROUND_1, final, third_place], third_place_match=True)


def complete_four() -> RemixState:
    return remix_state(finished(third_place_match=True), third_place_match=True)


@pytest.mark.parametrize(
    ("entries", "standing", "message"),
    [
        pytest.param(
            [*entries_for(range(1, 9)), *entries_for([8])],
            [],
            "given twice",
            id="entry-twice",
        ),
        pytest.param(
            [
                *entries_for(range(1, 9)),
                PlacingEntry(entry_id=eid(9), player_ids=(pid(9), pid(10))),
            ],
            [],
            "not a single player",
            id="pair-entry",
        ),
        pytest.param(
            [
                *entries_for(range(1, 9)),
                PlacingEntry(entry_id=eid(9), player_ids=(pid(8),)),
            ],
            [],
            "given twice",
            id="player-in-two-entries",
        ),
        pytest.param(
            entries_for(range(1, 9)),
            [[eid(1)], [eid(1)]],
            "given twice",
            id="standing-twice",
        ),
        pytest.param(
            entries_for(range(1, 9)), [[eid(42)]], "not among the entries", id="unknown"
        ),
        pytest.param(entries_for(range(1, 8)), [], "have no entry", id="no-entry"),
        pytest.param(
            entries_for(range(1, 10)), [], "left without a place", id="not-in-standing"
        ),
    ],
)
def test_place_remix_players_refuses_bad_entries(
    entries: list[PlacingEntry], standing: list[list[EntryId]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        place_remix_players(complete_four(), entries=entries, standing=standing)


def test_fr037_place_remix_players_needs_a_complete_knockout() -> None:
    with pytest.raises(ValueError, match="not complete"):
        place_remix_players(
            remix_state(FOUR_PAIRS_ROUND_1, third_place_match=False),
            entries=entries_for(range(1, 9)),
        )


def row(n: int, place: int, partner: int | None = None) -> RemixPlace:
    return RemixPlace(
        entry_id=eid(n),
        player_id=pid(n),
        place=place,
        partner_id=None if partner is None else pid(partner),
    )


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        pytest.param(
            [row(1, 1, 2), row(2, 1, 1), row(1, 2)], "given twice", id="twice"
        ),
        pytest.param([row(1, 1, 2)], "not placed with them", id="partner-missing"),
        pytest.param(
            [row(1, 1, 2), row(2, 2, 1)], "not placed with them", id="other-place"
        ),
        pytest.param(
            [row(1, 1, 2), row(2, 1, 3), row(3, 1, 2)],
            "not placed with them",
            id="other-partner",
        ),
        pytest.param([row(1, 1, 2), row(2, 1, 1), row(3, 3)], "gap", id="BR-104-gap"),
    ],
)
def test_remix_season_points_refuses_bad_places(
    rows: list[RemixPlace], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        remix_season_points(rows, DEFAULT_TABLE)


# Properties


def expected_counts(state: RemixState) -> list[int]:
    """Players per knockout place, best first, from the round structure (BR-102)."""
    counts = [2 for _ in state.newest_round for _ in range(2)]
    last = -2 if state.third_place_match else -1
    for round_ in reversed(state.rounds[:last]):
        played = sum(not m.has_bye for m in round_)
        if played:
            counts.append(2 * played)
    return counts


@st.composite
def knockouts(draw: st.DrawFn) -> tuple[int, bool, list[bool], bytes, int]:
    pairs = draw(st.integers(min_value=2, max_value=16))
    third_place_match = pairs >= 4 and draw(st.booleans())
    flips = draw(st.lists(st.booleans(), min_size=40, max_size=40))
    rng_seed = draw(st.binary(min_size=16, max_size=16))
    others = draw(st.integers(min_value=0, max_value=3))
    return pairs, third_place_match, flips, rng_seed, others


def check_places(rows: Sequence[RemixPlace], knockout_counts: list[int]) -> None:
    by_place = Counter(r.place for r in rows)
    units = {
        place: sum(0.5 if r.partner_id else 1 for r in rows if r.place == place)
        for place in by_place
    }
    expected = 1
    for place in sorted(by_place):
        assert place == expected  # BR-104
        expected += int(units[place])
    assert [by_place[p] for p in sorted(by_place)][
        : len(knockout_counts)
    ] == knockout_counts


@settings(deadline=None)
@given(knockouts())
def test_br140_br145_a_knockout_drawn_round_after_round_places_everybody(
    case: tuple[int, bool, list[bool], bytes, int],
) -> None:
    pairs, third_place_match, flips, rng_seed, others = case
    players = range(1, 2 * pairs + others + 1)

    state = remix_state(
        play_out(
            pairs, third_place_match=third_place_match, flips=flips, rng_seed=rng_seed
        ),
        third_place_match=third_place_match,
    )
    rows = place_remix_players(
        state, entries=entries_for(players), standing=standing_of(players)
    )

    assert state.is_complete
    assert sorted(r.player_id.int for r in rows) == list(players)
    check_places(rows, expected_counts(state))
    assert len(remix_season_points(rows, DEFAULT_TABLE)) == len(rows)
