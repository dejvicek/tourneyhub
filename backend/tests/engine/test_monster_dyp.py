import itertools
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import replace
from functools import cache
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tourneyhub.engine.errors import (
    NotEnoughPlayersError,
    OddQualifierCountError,
    QualifierCountError,
)
from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.monster_dyp import (
    DEFAULT_OPTIONS,
    GroupingMethod,
    MonsterDraw,
    MonsterDypOptions,
    MonsterMatch,
    MonsterRound,
    MonsterStanding,
    TopPlayerOrder,
    draw_monster_round,
    knockout_purpose,
    monster_standings,
    select_monster_knockout,
    sit_out_purpose,
    swap_purpose,
)
from tourneyhub.engine.results import tiebreak_purpose
from tourneyhub.engine.tournaments import (
    DEFAULT_TIEBREAKERS,
    MatchOutcome,
    MonsterKnockoutMode,
    Tiebreaker,
)

SEED = bytes(range(16))

type Teams = tuple[tuple[int, int], tuple[int, int]]


def pid(n: int) -> PlayerId:
    return PlayerId(UUID(int=n))


def players(count: int) -> tuple[PlayerId, ...]:
    """Players 1 to `count`, whose ids are their numbers."""
    return tuple(pid(n) for n in range(1, count + 1))


def game(
    team_1: tuple[int, int],
    team_2: tuple[int, int],
    outcome: MatchOutcome | None = None,
    score_difference: int = 0,
) -> MonsterMatch:
    return MonsterMatch(
        team_1=(pid(team_1[0]), pid(team_1[1])),
        team_2=(pid(team_2[0]), pid(team_2[1])),
        outcome=outcome,
        score_difference=score_difference,
    )


def rounds_of(*matches: Sequence[Teams]) -> tuple[MonsterRound, ...]:
    """Rounds 1 to n, each with the given teams and no result."""
    return tuple(
        MonsterRound(round_no=number, matches=tuple(game(*teams) for teams in round_))
        for number, round_ in enumerate(matches, start=1)
    )


def sitting_out_in_turn(round_count: int) -> tuple[MonsterRound, ...]:
    """Five players; in round n player n sits out and the other four play."""
    rounds = []
    for number in range(1, round_count + 1):
        a, b, c, d = sorted(set(range(1, 6)) - {number})
        rounds.append(
            MonsterRound(
                round_no=number, matches=(game((a, d), (b, c)),), sat_out=(pid(number),)
            )
        )
    return tuple(rounds)


def numbers(draw: MonsterDraw) -> list[Teams]:
    def team(pair: tuple[PlayerId, PlayerId]) -> tuple[int, int]:
        return pair[0].int, pair[1].int

    return [(team(group.team_1), team(group.team_2)) for group in draw.groups]


def draw_round(
    count: int,
    rounds: Iterable[MonsterRound] = (),
    *,
    standing: Sequence[int] | None = None,
    league_ranking: Sequence[int] | None = None,
    marked: Iterable[int] = (),
    disabled: Iterable[int] = (),
    options: MonsterDypOptions = DEFAULT_OPTIONS,
) -> MonsterDraw:
    order = players(count) if standing is None else tuple(map(pid, standing))
    return draw_monster_round(
        order,
        rounds,
        league_ranking=(
            players(count)
            if league_ranking is None
            else tuple(map(pid, league_ranking))
        ),
        rng_seed=SEED,
        marked_top_players=map(pid, marked),
        disabled=map(pid, disabled),
        options=options,
    )


def partnerships(rounds: Iterable[MonsterRound]) -> Counter[frozenset[PlayerId]]:
    """How many times each pair of players have been partners."""
    return Counter(
        frozenset(team)
        for round_ in rounds
        for match in round_.matches
        for team in (match.team_1, match.team_2)
    )


def earlier_counts(draw: MonsterDraw, before: Iterable[MonsterRound]) -> list[int]:
    """How often each team of the draw has been partners before, counted afresh."""
    counts = partnerships(before)
    return [
        counts[frozenset(team)]
        for group in draw.groups
        for team in (group.team_1, group.team_2)
    ]


def repeats(draw: MonsterDraw, before: Iterable[MonsterRound]) -> int:
    """The draw's teams that were partners before, not read from the engine's flags."""
    return sum(count > 0 for count in earlier_counts(draw, before))


def repeat_order(counts: Iterable[int]) -> tuple[int, ...]:
    """The earlier counts of the repeated teams, highest first (ADR-011).

    Of two draws, the one whose tuple is less is the better: it has fewer
    teams at the highest count, then at the next count down, and so on, and
    with the same counts a draw with fewer repeated teams is a prefix.
    """
    return tuple(sorted((count for count in counts if count), reverse=True))


def best_repeat_order(
    playing: Sequence[PlayerId],
    partners: Counter[frozenset[PlayerId]],
    top_players: Iterable[PlayerId] = (),
) -> tuple[int, ...]:
    """The best `repeat_order` of any teams; empty when no team must repeat.

    Two top players are never together.
    """
    tops = set(top_players)

    @cache
    def best(free: frozenset[PlayerId]) -> tuple[int, ...]:
        if not free:
            return ()
        first = min(free)
        rest = free - {first}
        return min(
            (
                repeat_order((partners[frozenset((first, other))], *tail))
                for other in rest
                if not (first in tops and other in tops)
                for tail in (best(rest - {other}),)
            ),
            default=(sys.maxsize,),  # a dead end: worse than any real grouping
        )

    return best(frozenset(playing))


def pairings(free: Sequence[PlayerId]) -> Iterator[list[frozenset[PlayerId]]]:
    """Every way to split the players into teams of two."""
    if not free:
        yield []
        return
    first, *rest = free
    for other in rest:
        remaining = [player for player in rest if player != other]
        for tail in pairings(remaining):
            yield [frozenset((first, other)), *tail]


def spread(
    before: Counter[frozenset[PlayerId]],
    teams: Iterable[frozenset[PlayerId]],
    count: int,
) -> int:
    """Highest minus lowest partnership count over all pairs, after the teams play."""
    after = before + Counter(teams)
    values = [
        after[frozenset(pair)] for pair in itertools.combinations(players(count), 2)
    ]
    return max(values) - min(values)


def line(player: int, position: int, place: int | None = None) -> MonsterStanding:
    return MonsterStanding(
        player_id=pid(player),
        position=position,
        place=position if place is None else place,
        points=0,
        bh1=0,
        bh2=0,
        score_difference=0,
        played=0,
        won=0,
        drawn=0,
        lost=0,
        sat_out=0,
        is_decided_by_lot=place is not None,
    )


def table(count: int) -> tuple[MonsterStanding, ...]:
    """A standing where player n is at position n, every place its own."""
    return tuple(line(n, n) for n in range(1, count + 1))


def knockout_numbers(
    standings: Sequence[MonsterStanding], *, qualifiers: int, mode: MonsterKnockoutMode
) -> list[tuple[int, ...]]:
    result = select_monster_knockout(
        standings, qualifiers=qualifiers, mode=mode, rng_seed=SEED, draw_counter=0
    )
    return [tuple(id_.int for id_ in entry.player_ids) for entry in result.entries]


# ---------------------------------------------------------------- purposes


def test_adr010_lot_purposes() -> None:
    assert tiebreak_purpose(3) == "tiebreak:after-round-3"
    assert sit_out_purpose(4) == "sit-out:round-4"
    assert swap_purpose(5) == "monster-swap:round-5"
    assert knockout_purpose(MonsterKnockoutMode.LORD_HAVE_MERCY, 2) == (
        "lord_have_mercy:2"
    )


# ---------------------------------------------------------------- standings


def test_br070_both_players_of_a_team_get_the_points() -> None:
    rounds = [
        MonsterRound(
            round_no=1, matches=(game((1, 4), (2, 3), MatchOutcome.SIDE_1, 3),)
        )
    ]

    result = monster_standings(
        players(4), rounds, tiebreakers=(), sit_out_points=0, rng_seed=SEED
    )

    by_player = {line.player_id.int: line for line in result}
    assert [by_player[n].points for n in (1, 2, 3, 4)] == [2, 0, 0, 2]
    assert [by_player[n].score_difference for n in (1, 2, 3, 4)] == [3, -3, -3, 3]
    assert (by_player[1].won, by_player[2].lost, by_player[1].played) == (1, 1, 1)


def test_br070_a_draw_gives_every_player_a_point() -> None:
    rounds = [
        MonsterRound(round_no=1, matches=(game((1, 4), (2, 3), MatchOutcome.DRAW),))
    ]

    result = monster_standings(
        players(4), rounds, tiebreakers=(), sit_out_points=0, rng_seed=SEED
    )

    assert {line.points for line in result} == {1}
    assert {line.drawn for line in result} == {1}


def test_br073_bh1_sums_both_opponents_and_bh2_their_bh1() -> None:
    rounds = [
        MonsterRound(round_no=1, matches=(game((1, 4), (2, 3), MatchOutcome.SIDE_2),))
    ]

    result = monster_standings(
        players(4), rounds, tiebreakers=(), sit_out_points=0, rng_seed=SEED
    )

    by_player = {line.player_id.int: line for line in result}
    assert (by_player[1].bh1, by_player[2].bh1) == (4, 0)
    assert (by_player[1].bh2, by_player[2].bh2) == (0, 8)


@pytest.mark.parametrize("sit_out_points", [0, 1, 2])
def test_br076_a_sit_out_earns_the_sit_out_points(sit_out_points: int) -> None:
    rounds = [
        MonsterRound(
            round_no=1,
            matches=(game((1, 4), (2, 3), MatchOutcome.SIDE_1),),
            sat_out=(pid(5),),
        )
    ]

    result = monster_standings(
        players(5),
        rounds,
        tiebreakers=(),
        sit_out_points=sit_out_points,
        rng_seed=SEED,
    )

    five = next(line for line in result if line.player_id == pid(5))
    assert (five.points, five.sat_out, five.played, five.bh1) == (
        sit_out_points,
        1,
        0,
        0,
    )


@pytest.mark.parametrize("sit_out_points", [0, 1, 2])
def test_br076_br077_each_sit_out_counts_as_soon_as_its_round_is_drawn(
    sit_out_points: int,
) -> None:
    rounds = [
        MonsterRound(
            round_no=1,
            matches=(game((1, 4), (2, 3)),),
            sat_out=(pid(5), pid(6)),
        )
    ]

    result = monster_standings(
        players(6),
        rounds,
        tiebreakers=(),
        sit_out_points=sit_out_points,
        rng_seed=SEED,
    )

    by_player = {line.player_id.int: line for line in result}
    for sitting_out in (5, 6):
        line = by_player[sitting_out]
        assert (line.points, line.sat_out, line.played) == (sit_out_points, 1, 0)
    assert (by_player[1].points, by_player[1].played) == (0, 0)


def test_br077_each_player_who_sits_out_gets_2_points_that_bh1_and_bh2_sum() -> None:
    rounds = [
        MonsterRound(
            round_no=1,
            matches=(game((1, 4), (2, 3), MatchOutcome.SIDE_1),),
            sat_out=(pid(5),),
        ),
        MonsterRound(
            round_no=2,
            matches=(game((5, 2), (1, 3), MatchOutcome.SIDE_1),),
            sat_out=(pid(4),),
        ),
    ]

    result = monster_standings(
        players(5),
        rounds,
        tiebreakers=DEFAULT_TIEBREAKERS,
        sit_out_points=2,
        rng_seed=SEED,
    )

    by_player = {line.player_id: line for line in result}
    assert {p.int: by_player[p].points for p in by_player} == {
        1: 2,
        2: 2,
        3: 0,
        4: 4,
        5: 4,
    }
    assert {p.int: by_player[p].bh1 for p in by_player} == {
        1: 8,
        2: 8,
        3: 12,
        4: 2,
        5: 2,
    }
    assert {p.int: by_player[p].bh2 for p in by_player} == {
        1: 30,
        2: 30,
        3: 20,
        4: 20,
        5: 20,
    }


def test_br073_a_match_without_a_result_counts_for_nothing() -> None:
    result = monster_standings(
        players(4),
        rounds_of([((1, 4), (2, 3))]),
        tiebreakers=DEFAULT_TIEBREAKERS,
        sit_out_points=0,
        rng_seed=SEED,
    )

    assert {(line.points, line.played, line.bh1) for line in result} == {(0, 0, 0)}


def test_br072_tie_breakers_apply_in_the_organizers_order() -> None:
    # 1+2 beat 3+4 by 1; 5+6 lost to 7+8 by 5. 1, 2, 7 and 8 have 2 points.
    rounds = [
        MonsterRound(
            round_no=1,
            matches=(
                game((1, 2), (3, 4), MatchOutcome.SIDE_1, 1),
                game((5, 6), (7, 8), MatchOutcome.SIDE_2, -5),
            ),
        )
    ]

    by_difference = monster_standings(
        players(8),
        rounds,
        tiebreakers=(Tiebreaker.SCORE_DIFFERENCE,),
        sit_out_points=0,
        rng_seed=SEED,
    )

    assert {line.player_id.int for line in by_difference[:2]} == {7, 8}
    assert [line.place for line in by_difference] == [1, 1, 3, 3, 5, 5, 7, 7]


def test_br074_level_players_share_the_place_and_the_lot_orders_them() -> None:
    rounds = [
        MonsterRound(round_no=1, matches=(game((1, 4), (2, 3), MatchOutcome.SIDE_1),))
    ]

    result = monster_standings(
        players(4), rounds, tiebreakers=(), sit_out_points=0, rng_seed=SEED
    )

    assert [line.place for line in result] == [1, 1, 3, 3]
    assert all(line.is_decided_by_lot for line in result)
    winners = order_by_lot(
        (pid(1), pid(4)), rng_seed=SEED, purpose="tiebreak:after-round-1"
    )
    assert tuple(line.player_id for line in result[:2]) == winners


@pytest.mark.parametrize(
    ("rounds", "tiebreakers", "sit_out_points"),
    [
        pytest.param(rounds_of([]), (Tiebreaker.BH1, Tiebreaker.BH1), 0, id="tb-twice"),
        pytest.param(rounds_of([]), (), 3, id="sit-out-points"),
        pytest.param([MonsterRound(round_no=2, matches=())], (), 0, id="round-numbers"),
        pytest.param(rounds_of([((1, 2), (1, 3))]), (), 0, id="player-twice"),
        pytest.param(rounds_of([((1, 2), (3, 9))]), (), 0, id="unknown-player"),
    ],
)
def test_standings_refuse_a_caller_bug(
    rounds: Sequence[MonsterRound],
    tiebreakers: tuple[Tiebreaker, ...],
    sit_out_points: int,
) -> None:
    with pytest.raises(ValueError):  # noqa: PT011  # every caller bug is a ValueError
        monster_standings(
            players(4),
            rounds,
            tiebreakers=tiebreakers,
            sit_out_points=sit_out_points,
            rng_seed=SEED,
        )


# ---------------------------------------------------------------- groups


def test_br060_round_1_groups_by_league_ranking_with_top_players_first() -> None:
    result = draw_round(8)

    assert numbers(result) == [((1, 5), (3, 4)), ((2, 8), (6, 7))]
    assert [group.top_player for group in result.groups] == [pid(1), pid(2)]
    assert result.method is GroupingMethod.STANDING
    assert (result.round_no, result.sitting_out) == (1, ())


def test_br061_sixteen_players_with_four_top_players() -> None:
    result = draw_round(16)

    # #1 #5 #6 #7 · #2 #8 #9 #10 · #3 #11 #12 #13 · #4 #14 #15 #16
    assert numbers(result) == [
        ((1, 7), (5, 6)),
        ((2, 10), (8, 9)),
        ((3, 13), (11, 12)),
        ((4, 16), (14, 15)),
    ]
    assert result.top_players == (pid(1), pid(2), pid(3), pid(4))


def test_br060_from_round_3_groups_of_four_by_standing() -> None:
    rounds = rounds_of(
        [((1, 2), (3, 4)), ((5, 6), (7, 8))], [((1, 3), (2, 4)), ((5, 7), (6, 8))]
    )

    result = draw_round(8, rounds)

    assert numbers(result) == [((1, 4), (2, 3)), ((5, 8), (6, 7))]
    assert result.top_players == ()
    assert all(group.top_player is None for group in result.groups)


def test_br061_round_2_takes_top_players_by_league_ranking() -> None:
    rounds = rounds_of([((1, 4), (2, 3)), ((5, 8), (6, 7))])

    result = draw_round(8, rounds, standing=(5, 6, 1, 2, 3, 4, 7, 8))

    assert result.top_players == (pid(1), pid(2))
    assert numbers(result) == [((1, 3), (5, 6)), ((2, 8), (4, 7))]


def test_fr041_the_standing_order_sorts_only_the_marked_top_players() -> None:
    rounds = rounds_of([((1, 4), (2, 3)), ((5, 8), (6, 7))])
    by_standing = MonsterDypOptions(top_player_order=TopPlayerOrder.STANDING)

    result = draw_round(
        8, rounds, standing=(5, 6, 1, 2, 3, 4, 7, 8), marked=[2, 6], options=by_standing
    )

    assert result.top_players == (pid(6), pid(2))
    assert numbers(result) == [((6, 3), (5, 1)), ((2, 8), (4, 7))]


def test_fr041_unmarked_top_players_always_follow_the_league_ranking() -> None:
    rounds = rounds_of([((1, 4), (2, 3)), ((5, 8), (6, 7))])
    by_standing = MonsterDypOptions(top_player_order=TopPlayerOrder.STANDING)

    unmarked = draw_round(
        8, rounds, standing=(5, 6, 1, 2, 3, 4, 7, 8), options=by_standing
    )
    one_marked = draw_round(
        8, rounds, standing=(5, 6, 1, 2, 3, 4, 7, 8), marked=[6], options=by_standing
    )

    assert unmarked.top_players == (pid(1), pid(2))
    assert one_marked.top_players == (pid(6), pid(1))


def test_fr041_marked_top_players_come_first() -> None:
    result = draw_round(8, marked=[7])

    assert result.top_players == (pid(7), pid(1))
    assert numbers(result) == [((7, 4), (2, 3)), ((1, 8), (5, 6))]


def test_fr041_more_marked_than_matches_take_the_league_ranking_order() -> None:
    result = draw_round(8, marked=[8, 5, 3])

    assert result.top_players == (pid(3), pid(5))


# ---------------------------------------------------------------- sit-outs


def test_br063_the_extra_players_sit_out_by_lot() -> None:
    result = draw_round(6)

    lot = order_by_lot(players(6), rng_seed=SEED, purpose="sit-out:round-1")
    assert result.sitting_out == lot[:2]
    assert result.is_sit_out_by_lot
    assert len(result.groups) == 1


def test_br063_those_who_sat_out_the_fewest_times_sit_out() -> None:
    rounds = sitting_out_in_turn(4)

    result = draw_round(5, rounds)

    assert result.sitting_out == (pid(5),)
    assert not result.is_sit_out_by_lot


def test_br064_disabled_players_neither_play_nor_sit_out() -> None:
    result = draw_round(6, disabled=[2, 5])

    assert result.sitting_out == ()
    assert numbers(result) == [((1, 6), (3, 4))]


def test_br063_a_round_needs_four_players_who_are_not_disabled() -> None:
    with pytest.raises(NotEnoughPlayersError) as raised:
        draw_round(5, disabled=[1, 2])

    assert (raised.value.minimum, raised.value.given) == (4, 3)


def test_open_rule_top_players_exempt_from_the_sit_out_lot() -> None:
    exempt = MonsterDypOptions(are_top_players_exempt=True)

    result = draw_round(5, options=exempt)

    lot = order_by_lot(players(5)[1:], rng_seed=SEED, purpose="sit-out:round-1")
    assert result.sitting_out == lot[:1]
    assert result.top_players == (pid(1),)


def test_open_rule_top_players_not_exempt_by_default() -> None:
    result = draw_round(5)

    lot = order_by_lot(players(5), rng_seed=SEED, purpose="sit-out:round-1")
    assert result.sitting_out == lot[:1]
    assert result.top_players == (min(set(players(5)) - set(lot[:1])),)


@pytest.mark.parametrize(
    "avoids", [pytest.param(True, id="avoids"), pytest.param(False, id="prd")]
)
def test_open_rule_not_sitting_out_twice_in_a_row(*, avoids: bool) -> None:
    # Everyone has sat out once; player 5 sat out the last round.
    rounds = sitting_out_in_turn(5)
    options = MonsterDypOptions(avoids_sitting_out_twice_in_a_row=avoids)

    result = draw_round(5, rounds, options=options)

    candidates = players(4) if avoids else players(5)
    lot = order_by_lot(candidates, rng_seed=SEED, purpose="sit-out:round-6")
    assert result.sitting_out == lot[:1]
    assert result.is_sit_out_by_lot


# ---------------------------------------------------------------- repeated partners


def test_br062_the_nearest_swap_avoids_a_repeated_partner() -> None:
    # (1, 4) would repeat; swapping 3 and 2 or 1 and 2 brings back (1, 3) or
    # (2, 4), so 4 and 5 swap.
    rounds = rounds_of([((1, 4), (5, 6))], [((1, 3), (2, 4))], [((7, 8), (2, 6))])

    result = draw_round(8, rounds)

    assert numbers(result) == [((1, 5), (2, 3)), ((4, 8), (6, 7))]
    assert result.method is GroupingMethod.SWAPS
    assert repeats(result, rounds) == 0
    assert not result.is_grouping_by_lot


def test_adr011_the_lot_chooses_between_equally_good_swaps() -> None:
    rounds = rounds_of([((1, 4), (5, 6))], [((7, 8), (2, 6))], [((1, 2), (3, 5))])

    result = draw_round(8, rounds)

    assert repeats(result, rounds) == 0
    assert result.is_grouping_by_lot


def test_br062_a_matching_finds_new_partners_when_the_swaps_get_stuck() -> None:
    rounds = rounds_of(
        [((3, 2), (6, 1)), ((5, 8), (7, 4))],
        [((1, 7), (8, 4)), ((3, 5), (2, 6))],
        [((2, 1), (7, 4)), ((8, 3), (5, 6))],
        [((4, 1), (7, 5)), ((6, 3), (8, 2))],
    )

    result = draw_round(8, rounds)

    assert result.method is GroupingMethod.MATCHING
    assert numbers(result) == [((2, 4), (1, 5)), ((3, 7), (6, 8))]
    assert repeats(result, rounds) == 0


def test_br062_when_every_grouping_repeats_the_draw_has_the_fewest() -> None:
    rounds = rounds_of(
        [((6, 5), (3, 7)), ((8, 2), (1, 4))],
        [((8, 5), (7, 2)), ((4, 6), (1, 3))],
        [((1, 6), (2, 8)), ((5, 7), (3, 4))],
        [((2, 7), (6, 8)), ((4, 5), (3, 1))],
        [((2, 6), (1, 5)), ((7, 3), (4, 8))],
        [((8, 1), (3, 4)), ((2, 5), (7, 6))],
    )

    result = draw_round(8, rounds)

    assert result.method is GroupingMethod.MATCHING
    assert numbers(result) == [((1, 6), (2, 4)), ((7, 8), (3, 5))]
    best = best_repeat_order(players(8), partnerships(rounds))
    assert best
    assert repeat_order(earlier_counts(result, rounds)) == best


def test_br062_a_partnership_played_twice_is_avoided_before_one_played_once() -> None:
    # 1+4 and 2+3 have partnered twice, every other pair once: each of the
    # three groupings repeats two teams, so the fewer earlier counts decide.
    rounds = rounds_of(
        [((1, 4), (2, 3))],
        [((1, 3), (2, 4))],
        [((1, 2), (3, 4))],
        [((1, 4), (2, 3))],
    )

    result = draw_round(4, rounds, standing=(1, 2, 3, 4))

    assert numbers(result) != [((1, 4), (2, 3))]
    assert repeats(result, rounds) == 2
    assert earlier_counts(result, rounds) == [1, 1]
    assert result.method is GroupingMethod.SWAPS


def test_br062_adr011_no_third_time_while_teams_could_partner_a_second_time() -> None:
    # Issue #79 (6 players, round 7). 1, 3, 4 and 5 play, and every grouping
    # repeats a partner: 3+4 have partnered twice, 1+5 never and the other four
    # teams once. 1+5 v 3+4 would have 3+4 partner a third time, so two teams
    # that each partner a second time are drawn instead.
    rounds = rounds_of(
        [((6, 1), (5, 2))],
        [((3, 4), (2, 6))],
        [((3, 1), (4, 5))],
        [((5, 6), (1, 4))],
        [((5, 3), (6, 2))],
        [((1, 2), (4, 3))],
    )

    result = draw_round(6, rounds, standing=(1, 4, 5, 3, 2, 6), disabled=(2, 6))

    assert numbers(result) == [((1, 3), (4, 5))]
    assert earlier_counts(result, rounds) == [1, 1]
    assert result.method is GroupingMethod.STANDING

    # From 1+5 v 3+4, the swaps leave it too.
    swapped = draw_round(6, rounds, standing=(1, 3, 4, 5, 2, 6), disabled=(2, 6))

    assert numbers(swapped) == [((1, 4), (3, 5))]
    assert earlier_counts(swapped, rounds) == [1, 1]
    assert swapped.method is GroupingMethod.SWAPS


# ---------------------------------------------------------------- draw caller bugs


@pytest.mark.parametrize(
    ("standing", "league_ranking", "marked", "disabled"),
    [
        pytest.param((1, 1, 2, 3), (1, 2, 3), (), (), id="player-twice"),
        pytest.param((1, 2, 3, 4), (1, 2, 3, 5), (), (), id="other-ranking"),
        pytest.param((1, 2, 3, 4), (1, 2, 3, 4), (9,), (), id="unknown-marked"),
        pytest.param((1, 2, 3, 4), (1, 2, 3, 4), (), (9,), id="unknown-disabled"),
    ],
)
def test_the_draw_refuses_a_caller_bug(
    standing: tuple[int, ...],
    league_ranking: tuple[int, ...],
    marked: tuple[int, ...],
    disabled: tuple[int, ...],
) -> None:
    with pytest.raises(ValueError):  # noqa: PT011  # every caller bug is a ValueError
        draw_round(
            4,
            standing=standing,
            league_ranking=league_ranking,
            marked=marked,
            disabled=disabled,
        )


# ---------------------------------------------------------------- knockout


def test_br081_seeded_pairs_with_sixteen() -> None:
    result = knockout_numbers(
        table(20), qualifiers=16, mode=MonsterKnockoutMode.SEEDED_PAIRS
    )

    assert result == [(n, n + 8) for n in range(1, 9)]


def test_prd_5_2_seeded_pairs_for_the_top_8() -> None:
    result = knockout_numbers(
        table(15), qualifiers=8, mode=MonsterKnockoutMode.SEEDED_PAIRS
    )

    assert result == [(1, 5), (2, 6), (3, 7), (4, 8)]


def test_br082_singles_are_seeded_by_place() -> None:
    result = select_monster_knockout(
        table(6),
        qualifiers=3,
        mode=MonsterKnockoutMode.SINGLES,
        rng_seed=SEED,
        draw_counter=0,
    )

    assert [entry.player_ids for entry in result.entries] == [
        (pid(1),),
        (pid(2),),
        (pid(3),),
    ]
    assert [entry.seed for entry in result.entries] == [1, 2, 3]
    assert not any(entry.is_drawn_by_lot for entry in result.entries)


def test_br083_a_little_mercy_draws_bottom_half_partners() -> None:
    result = select_monster_knockout(
        table(8),
        qualifiers=8,
        mode=MonsterKnockoutMode.A_LITTLE_MERCY,
        rng_seed=SEED,
        draw_counter=1,
    )

    drawn = order_by_lot(players(8)[4:], rng_seed=SEED, purpose="a_little_mercy:1")
    assert [entry.player_ids for entry in result.entries] == [
        (pid(n), partner) for n, partner in zip(range(1, 5), drawn, strict=True)
    ]
    assert all(entry.is_drawn_by_lot for entry in result.entries)


def test_br084_lord_have_mercy_pairs_and_seeds_by_lot() -> None:
    result = select_monster_knockout(
        table(8),
        qualifiers=8,
        mode=MonsterKnockoutMode.LORD_HAVE_MERCY,
        rng_seed=SEED,
        draw_counter=0,
    )

    drawn = order_by_lot(players(8), rng_seed=SEED, purpose="lord_have_mercy:0")
    assert [set(entry.player_ids) for entry in result.entries] == [
        set(drawn[index : index + 2]) for index in range(0, 8, 2)
    ]
    assert all(
        entry.player_ids[0].int < entry.player_ids[1].int for entry in result.entries
    )


def test_br080_disabled_players_do_not_qualify_and_the_next_move_up() -> None:
    result = select_monster_knockout(
        table(6),
        qualifiers=4,
        mode=MonsterKnockoutMode.SEEDED_PAIRS,
        rng_seed=SEED,
        draw_counter=0,
        disabled=[pid(2), pid(6)],
    )

    assert result.qualifiers == (pid(1), pid(3), pid(4), pid(5))
    assert result.skipped == (pid(2),)
    assert [entry.player_ids for entry in result.entries] == [
        (pid(1), pid(4)),
        (pid(3), pid(5)),
    ]
    assert result.mode is MonsterKnockoutMode.SEEDED_PAIRS


def test_br074_the_lot_decides_the_cut_between_level_players() -> None:
    standings = (line(1, 1), line(2, 2, place=2), line(3, 3, place=2), line(4, 4))

    level = select_monster_knockout(
        standings,
        qualifiers=2,
        mode=MonsterKnockoutMode.SINGLES,
        rng_seed=SEED,
        draw_counter=0,
    )
    apart = select_monster_knockout(
        standings,
        qualifiers=3,
        mode=MonsterKnockoutMode.SINGLES,
        rng_seed=SEED,
        draw_counter=0,
    )

    assert level.is_cut_by_lot
    assert not apart.is_cut_by_lot


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        pytest.param(
            MonsterKnockoutMode.SINGLES, [False, True, True, False], id="singles"
        ),
        pytest.param(MonsterKnockoutMode.SEEDED_PAIRS, [True, True], id="seeded-pairs"),
    ],
)
def test_adr009_entries_that_follow_the_standing_note_a_lot_in_it(
    mode: MonsterKnockoutMode, expected: list[bool]
) -> None:
    standings = (line(1, 1), line(2, 2, place=2), line(3, 3, place=2), line(4, 4))

    result = select_monster_knockout(
        standings, qualifiers=4, mode=mode, rng_seed=SEED, draw_counter=0
    )

    assert [entry.is_drawn_by_lot for entry in result.entries] == expected


def test_adr009_seeded_pairs_without_a_lot_in_the_standing_are_not_drawn() -> None:
    result = select_monster_knockout(
        table(4),
        qualifiers=4,
        mode=MonsterKnockoutMode.SEEDED_PAIRS,
        rng_seed=SEED,
        draw_counter=0,
    )

    assert not any(entry.is_drawn_by_lot for entry in result.entries)


@pytest.mark.parametrize(
    ("qualifiers", "mode", "third_place_match", "minimum", "maximum"),
    [
        pytest.param(1, MonsterKnockoutMode.SINGLES, False, 2, 9, id="singles-1"),
        pytest.param(3, MonsterKnockoutMode.SINGLES, True, 4, 9, id="singles-third"),
        pytest.param(10, MonsterKnockoutMode.SINGLES, False, 2, 9, id="too-many"),
        pytest.param(2, MonsterKnockoutMode.SEEDED_PAIRS, False, 4, 8, id="one-pair"),
        pytest.param(
            6, MonsterKnockoutMode.LORD_HAVE_MERCY, True, 8, 8, id="pairs-3rd"
        ),
        pytest.param(10, MonsterKnockoutMode.A_LITTLE_MERCY, False, 4, 8, id="above"),
    ],
)
def test_br080_the_number_of_qualifiers_must_fit(
    qualifiers: int,
    mode: MonsterKnockoutMode,
    minimum: int,
    maximum: int,
    *,
    third_place_match: bool,
) -> None:
    with pytest.raises(QualifierCountError) as raised:
        select_monster_knockout(
            table(9),
            qualifiers=qualifiers,
            mode=mode,
            rng_seed=SEED,
            draw_counter=0,
            third_place_match=third_place_match,
        )

    assert (raised.value.minimum, raised.value.maximum) == (minimum, maximum)
    assert raised.value.given == qualifiers


def test_br080_pair_modes_need_an_even_number_of_qualifiers() -> None:
    with pytest.raises(OddQualifierCountError) as raised:
        select_monster_knockout(
            table(9),
            qualifiers=5,
            mode=MonsterKnockoutMode.A_LITTLE_MERCY,
            rng_seed=SEED,
            draw_counter=0,
        )

    assert raised.value.given == 5


@pytest.mark.parametrize(
    ("standings", "disabled"),
    [
        pytest.param((line(1, 1), line(1, 2)), (), id="player-twice"),
        pytest.param((line(1, 1), line(2, 3)), (), id="positions"),
        pytest.param(table(4), (pid(9),), id="unknown-disabled"),
    ],
)
def test_the_knockout_refuses_a_caller_bug(
    standings: Sequence[MonsterStanding], disabled: Sequence[PlayerId]
) -> None:
    with pytest.raises(ValueError):  # noqa: PT011  # every caller bug is a ValueError
        select_monster_knockout(
            standings,
            qualifiers=2,
            mode=MonsterKnockoutMode.SINGLES,
            rng_seed=SEED,
            draw_counter=0,
            disabled=disabled,
        )


# ---------------------------------------------------------------- properties


@st.composite
def tournaments(
    draw: st.DrawFn, *, max_players: int = 14, can_disable: bool = True
) -> tuple[int, int, MonsterDypOptions, frozenset[int], list[frozenset[int]], bytes]:
    count = draw(st.integers(min_value=4, max_value=max_players))
    round_count = draw(st.integers(min_value=1, max_value=8))
    options = MonsterDypOptions(
        are_top_players_exempt=draw(st.booleans()),
        top_player_order=draw(st.sampled_from(TopPlayerOrder)),
        avoids_sitting_out_twice_in_a_row=draw(st.booleans()),
    )
    marked = draw(st.frozensets(st.integers(min_value=1, max_value=count)))
    off_sets = st.frozensets(
        st.integers(min_value=1, max_value=count), max_size=count - 4
    )
    disabled = [
        draw(off_sets) if can_disable else frozenset() for _ in range(round_count)
    ]
    seed = draw(st.binary(min_size=16, max_size=16))
    return count, round_count, options, marked, disabled, seed


def play(
    count: int,
    round_count: int,
    options: MonsterDypOptions,
    marked: frozenset[int],
    disabled: Sequence[frozenset[int]],
    seed: bytes,
    outcomes: st.DataObject,
) -> list[tuple[MonsterDraw, tuple[MonsterRound, ...], frozenset[PlayerId]]]:
    """Play a whole tournament; return each draw with the rounds before it."""
    ids = players(count)
    ranking = tuple(reversed(ids))
    rounds: tuple[MonsterRound, ...] = ()
    history = []
    for number in range(1, round_count + 1):
        standing = (
            ranking
            if not rounds
            else tuple(
                line.player_id
                for line in monster_standings(
                    ids,
                    rounds,
                    tiebreakers=DEFAULT_TIEBREAKERS,
                    sit_out_points=0,
                    rng_seed=seed,
                )
            )
        )
        off = frozenset(map(pid, disabled[number - 1]))
        drawn = draw_monster_round(
            standing,
            rounds,
            league_ranking=ranking,
            rng_seed=seed,
            marked_top_players=map(pid, marked),
            disabled=off,
            options=options,
        )
        history.append((drawn, rounds, off))
        played = tuple(
            MonsterMatch(
                team_1=group.team_1,
                team_2=group.team_2,
                outcome=outcomes.draw(st.sampled_from(MatchOutcome)),
                score_difference=outcomes.draw(st.integers(-10, 10)),
            )
            for group in drawn.groups
        )
        rounds = (
            *rounds,
            MonsterRound(round_no=number, matches=played, sat_out=drawn.sitting_out),
        )
    return history


@settings(deadline=None)
@given(tournaments(), st.data())
def test_br060_to_br063_hold_in_every_round(
    tournament: tuple[
        int, int, MonsterDypOptions, frozenset[int], list[frozenset[int]], bytes
    ],
    data: st.DataObject,
) -> None:
    for drawn, before, off in play(*tournament, data):
        active = [player for player in players(tournament[0]) if player not in off]
        playing = [
            player
            for group in drawn.groups
            for player in (*group.team_1, *group.team_2)
        ]
        # Each active player plays once or sits out; the disabled do neither.
        assert sorted(playing + list(drawn.sitting_out)) == sorted(active)
        assert len(drawn.sitting_out) == len(active) % 4
        # BR-061: in rounds 1 and 2, one top player per group, as its 1st.
        if drawn.round_no <= 2:
            assert [group.top_player for group in drawn.groups] == list(
                drawn.top_players
            )
            assert all(group.team_1[0] == group.top_player for group in drawn.groups)
            assert drawn.method is not GroupingMethod.MATCHING
        else:
            assert drawn.top_players == ()
        # BR-062 and ADR-011: no grouping has fewer teams at a higher count.
        assert repeat_order(earlier_counts(drawn, before)) == best_repeat_order(
            playing, partnerships(before), drawn.top_players
        )
        # The flags the engine reports are the same teams, counted separately.
        assert [
            flag
            for group in drawn.groups
            for flag in (group.is_team_1_repeat, group.is_team_2_repeat)
        ] == [count > 0 for count in earlier_counts(drawn, before)]


@settings(deadline=None)
@given(tournaments(), st.data())
def test_br063_the_players_with_the_fewest_sit_outs_sit_out(
    tournament: tuple[
        int, int, MonsterDypOptions, frozenset[int], list[frozenset[int]], bytes
    ],
    data: st.DataObject,
) -> None:
    count, round_count, options, marked, disabled, seed = tournament
    # Exempt top players are the one open rule that sits others out instead.
    options = replace(options, are_top_players_exempt=False)
    sat_out: Counter[PlayerId] = Counter()
    history = play(count, round_count, options, marked, disabled, seed, data)
    for drawn, _, off in history:
        playing = {
            player
            for group in drawn.groups
            for player in (*group.team_1, *group.team_2)
        }
        assert not set(drawn.sitting_out) & off
        for sitting in drawn.sitting_out:
            assert all(sat_out[sitting] <= sat_out[other] for other in playing)
        sat_out.update(drawn.sitting_out)


@settings(deadline=None)
@given(tournaments(max_players=8, can_disable=False), st.data())
def test_br062_partnership_counts_stay_balanced_while_repeats_can_be_avoided(
    tournament: tuple[
        int, int, MonsterDypOptions, frozenset[int], list[frozenset[int]], bytes
    ],
    data: st.DataObject,
) -> None:
    for drawn, before, _ in play(*tournament, data):
        if drawn.top_players:
            continue  # rounds 1 and 2 keep the top players apart (BR-061)
        playing = [
            player
            for group in drawn.groups
            for player in (*group.team_1, *group.team_2)
        ]
        teams = [
            frozenset(team)
            for group in drawn.groups
            for team in (group.team_1, group.team_2)
        ]
        counts = partnerships(before)
        if best_repeat_order(playing, counts):
            # Every grouping repeats a partner. BR-062 does not rule on that
            # case; ADR-011 does, checked in test_br060_to_br063_hold_in_every_round.
            continue

        assert spread(counts, teams, tournament[0]) <= min(
            spread(counts, grouping, tournament[0]) for grouping in pairings(playing)
        )


@settings(deadline=None)
@given(tournaments(max_players=24, can_disable=False), st.data())
def test_br063_sit_outs_stay_balanced_and_dirac_rounds_never_repeat(
    tournament: tuple[
        int, int, MonsterDypOptions, frozenset[int], list[frozenset[int]], bytes
    ],
    data: st.DataObject,
) -> None:
    count = tournament[0]
    sat_out: Counter[PlayerId] = Counter()
    for drawn, before, _ in play(*tournament, data):
        sat_out.update(drawn.sitting_out)
        assert (
            max(sat_out[player] for player in players(count))
            - min(sat_out[player] for player in players(count))
            <= 1
        )
        # Each player has had at most r partners, so with n >= 2r + 2 players
        # who play a repeat-free grouping exists (Dirac, ADR-011).
        if count - len(drawn.sitting_out) >= 2 * len(before) + 2:
            assert repeats(drawn, before) == 0


@settings(deadline=None)
@given(tournaments(max_players=10), st.data())
def test_the_draw_is_deterministic(
    tournament: tuple[
        int, int, MonsterDypOptions, frozenset[int], list[frozenset[int]], bytes
    ],
    data: st.DataObject,
) -> None:
    count, _, options, marked, _, seed = tournament
    *_, (_, before, off) = play(*tournament, data)
    standing = players(count)

    def again(rounds: Sequence[MonsterRound]) -> MonsterDraw:
        return draw_monster_round(
            standing,
            rounds,
            league_ranking=tuple(reversed(standing)),
            rng_seed=seed,
            marked_top_players=sorted(map(pid, marked), reverse=True),
            disabled=sorted(off),
            options=options,
        )

    assert again(before) == again(tuple(reversed(before)))


@settings(deadline=None)
@given(tournaments(max_players=12), st.data())
def test_br070_to_br074_standings_are_consistent(
    tournament: tuple[
        int, int, MonsterDypOptions, frozenset[int], list[frozenset[int]], bytes
    ],
    data: st.DataObject,
) -> None:
    count, *_, seed = tournament
    *_, (_, rounds, _) = play(*tournament, data)
    tiebreakers = data.draw(st.permutations(DEFAULT_TIEBREAKERS))
    sit_out_points = data.draw(st.sampled_from((0, 1, 2)))

    result = monster_standings(
        players(count),
        reversed(rounds),
        tiebreakers=tiebreakers,
        sit_out_points=sit_out_points,
        rng_seed=seed,
    )

    results = sum(
        match.outcome is not None for round_ in rounds for match in round_.matches
    )
    sit_outs = sum(len(round_.sat_out) for round_ in rounds)
    assert sum(line.points for line in result) == 4 * results + sit_out_points * (
        sit_outs
    )
    assert sum(line.score_difference for line in result) == 0
    assert [line.position for line in result] == list(range(1, count + 1))
    shared = Counter(line.place for line in result)
    for line in result:
        assert line.is_decided_by_lot == (shared[line.place] > 1)
        assert line.place <= line.position
    for better, worse in itertools.pairwise(result):
        assert better.points >= worse.points
        if better.place == worse.place:
            assert better.points == worse.points


@given(
    st.integers(min_value=2, max_value=24),
    st.sampled_from(MonsterKnockoutMode),
    st.data(),
)
def test_br080_to_br084_every_mode_gives_valid_entries(
    count: int, mode: MonsterKnockoutMode, data: st.DataObject
) -> None:
    standings = table(count)
    disabled = data.draw(st.frozensets(st.sampled_from(players(count))))
    eligible = [player for player in players(count) if player not in disabled]
    pairs = mode is not MonsterKnockoutMode.SINGLES
    usable = len(eligible) - len(eligible) % 2 if pairs else len(eligible)
    minimum = 4 if pairs else 2
    if usable < minimum:
        return
    qualifiers = data.draw(
        st.integers(min_value=minimum, max_value=usable).filter(
            lambda n: not pairs or n % 2 == 0
        )
    )

    result = select_monster_knockout(
        standings,
        qualifiers=qualifiers,
        mode=mode,
        rng_seed=data.draw(st.binary(min_size=16, max_size=16)),
        draw_counter=data.draw(st.integers(min_value=0, max_value=5)),
        disabled=disabled,
    )

    entered = [player for entry in result.entries for player in entry.player_ids]
    assert sorted(entered) == sorted(eligible[:qualifiers])
    assert result.qualifiers == tuple(eligible[:qualifiers])
    assert [entry.seed for entry in result.entries] == list(
        range(1, len(result.entries) + 1)
    )
    assert {len(entry.player_ids) for entry in result.entries} == {2 if pairs else 1}
    if mode in {MonsterKnockoutMode.SEEDED_PAIRS, MonsterKnockoutMode.A_LITTLE_MERCY}:
        top_half = eligible[: qualifiers // 2]
        assert [entry.player_ids[0] for entry in result.entries] == top_half
