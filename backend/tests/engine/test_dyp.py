from dataclasses import replace
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.dyp import (
    DypHalf,
    DypHalves,
    check_hand_halves,
    draw_partners,
    split_halves_by_ranking,
)
from tourneyhub.engine.errors import (
    DypHalvesUnequalError,
    NotEnoughPlayersError,
    TooManyLeftOutError,
)
from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.ranking import RankedPlayer

SEED = bytes(range(16))


def pid(n: int) -> PlayerId:
    return PlayerId(UUID(int=n))


def ranking(*positions: int) -> list[RankedPlayer]:
    """Players whose ids are their league-ranking positions."""
    return [
        RankedPlayer(player_id=pid(p), position=p, is_decided_by_lot=False, tie_group=p)
        for p in positions
    ]


def tied(*groups: tuple[int, ...]) -> list[RankedPlayer]:
    """Players at positions 1 to n, where each group ties on every criterion."""
    players = []
    for group in groups:
        players += [
            RankedPlayer(
                player_id=pid(p),
                position=p,
                is_decided_by_lot=len(group) > 1,
                tie_group=group[0],
            )
            for p in group
        ]
    return players


def given_halves(top: tuple[int, ...], bottom: tuple[int, ...]) -> DypHalves:
    return DypHalves(
        top=tuple(map(pid, top)),
        bottom=tuple(map(pid, bottom)),
        left_out=None,
        is_left_out_by_lot=False,
        is_boundary_by_lot=False,
    )


def ints(players: tuple[PlayerId, ...]) -> list[int]:
    return [player.int for player in players]


def test_prd51_twelve_players_form_two_halves_of_six_and_six_pairs() -> None:
    # PRD §5.1 step 4: the 6 best-ranked players form the top half, the other
    # 6 the bottom half, and each top-half player is drawn a bottom partner.
    players = ranking(*range(12, 0, -1))

    halves = split_halves_by_ranking(players, rng_seed=SEED, draw_counter=0)
    pairs = draw_partners(halves, rng_seed=SEED, draw_counter=0)

    assert ints(halves.top) == [1, 2, 3, 4, 5, 6]
    assert ints(halves.bottom) == [7, 8, 9, 10, 11, 12]
    assert halves.left_out is None
    assert not halves.is_left_out_by_lot
    assert not halves.is_boundary_by_lot
    # The bottom order 7, 9, 12, 10, 8, 11 was also computed with shasum
    assert [(pair.top.int, pair.bottom.int) for pair in pairs] == [
        (1, 7),
        (2, 9),
        (3, 12),
        (4, 10),
        (5, 8),
        (6, 11),
    ]
    assert all(pair.is_drawn_by_lot for pair in pairs)


def test_br031_refuses_fewer_than_four_players_by_ranking() -> None:
    with pytest.raises(NotEnoughPlayersError) as raised:
        split_halves_by_ranking(ranking(1, 2, 3), rng_seed=SEED, draw_counter=0)

    assert (raised.value.minimum, raised.value.given) == (4, 3)


def test_br031_refuses_fewer_than_four_players_by_hand() -> None:
    halves = {pid(1): DypHalf.TOP, pid(2): DypHalf.BOTTOM, pid(3): DypHalf.LEFT_OUT}

    with pytest.raises(NotEnoughPlayersError) as raised:
        check_hand_halves(halves)

    assert (raised.value.minimum, raised.value.given) == (4, 3)


def test_br032_leaves_out_the_first_player_of_the_left_out_lot() -> None:
    players = ranking(*range(1, 8))
    drawn = order_by_lot(
        (ranked.player_id for ranked in players),
        rng_seed=SEED,
        purpose="dyp-left-out:2",
    )

    halves = split_halves_by_ranking(players, rng_seed=SEED, draw_counter=2)

    assert halves.left_out == drawn[0]
    assert halves.is_left_out_by_lot
    rest = [p for p in range(1, 8) if p != drawn[0].int]
    assert ints(halves.top) == rest[:3]
    assert ints(halves.bottom) == rest[3:]


def test_br032_accepts_equal_hand_halves_with_one_left_out() -> None:
    halves = {
        pid(5): DypHalf.TOP,
        pid(1): DypHalf.TOP,
        pid(2): DypHalf.BOTTOM,
        pid(4): DypHalf.BOTTOM,
        pid(3): DypHalf.LEFT_OUT,
    }

    checked = check_hand_halves(halves)

    assert checked == DypHalves(
        top=(pid(1), pid(5)),
        bottom=(pid(2), pid(4)),
        left_out=pid(3),
        is_left_out_by_lot=False,
        is_boundary_by_lot=False,
    )


def test_br032_refuses_unequal_hand_halves() -> None:
    halves = {pid(n): DypHalf.TOP for n in (1, 2, 3)} | {pid(4): DypHalf.BOTTOM}

    with pytest.raises(DypHalvesUnequalError) as raised:
        check_hand_halves(halves)

    assert (raised.value.top, raised.value.bottom) == (3, 1)


def test_br032_refuses_more_than_one_player_left_out() -> None:
    halves = {
        pid(1): DypHalf.TOP,
        pid(2): DypHalf.BOTTOM,
        pid(3): DypHalf.LEFT_OUT,
        pid(4): DypHalf.LEFT_OUT,
    }

    with pytest.raises(TooManyLeftOutError) as raised:
        check_hand_halves(halves)

    assert (raised.value.maximum, raised.value.given) == (1, 2)


def test_br032_odd_hand_halves_without_a_left_out_player_are_unequal() -> None:
    halves = {pid(n): DypHalf.TOP for n in (1, 2, 3)}
    halves |= {pid(n): DypHalf.BOTTOM for n in (4, 5)}

    with pytest.raises(DypHalvesUnequalError) as raised:
        check_hand_halves(halves)

    assert (raised.value.top, raised.value.bottom) == (3, 2)


def test_adr009_marks_a_boundary_the_ranking_lot_decided() -> None:
    players = tied((1,), (2,), (3, 4), (5,), (6,))

    halves = split_halves_by_ranking(players, rng_seed=SEED, draw_counter=0)

    assert halves.is_boundary_by_lot


def test_adr009_does_not_mark_a_boundary_between_two_different_ties() -> None:
    # Positions 3 and 4 were both decided by lot, but not against each other.
    players = tied((1,), (2, 3), (4, 5), (6,))

    halves = split_halves_by_ranking(players, rng_seed=SEED, draw_counter=0)

    assert not halves.is_boundary_by_lot


def test_br032_refuses_a_player_given_twice() -> None:
    players = [*ranking(1, 2, 3, 4), *ranking(4)]

    with pytest.raises(ValueError, match="twice"):
        split_halves_by_ranking(players, rng_seed=SEED, draw_counter=0)


def test_br033_draws_the_bottom_half_in_the_partner_lot_order() -> None:
    halves = given_halves((3, 1, 2), (4, 5, 6))
    drawn = order_by_lot(halves.bottom, rng_seed=SEED, purpose="dyp-partner:1")

    pairs = draw_partners(halves, rng_seed=SEED, draw_counter=1)

    assert tuple(pair.bottom for pair in pairs) == drawn
    assert ints(tuple(pair.top for pair in pairs)) == [1, 2, 3]


def test_br033_refuses_unequal_halves() -> None:
    halves = given_halves((1, 2), (3,))

    with pytest.raises(DypHalvesUnequalError):
        draw_partners(halves, rng_seed=SEED, draw_counter=0)


seeds = st.binary(min_size=16, max_size=16)
draw_counters = st.integers(min_value=0, max_value=1000)


@st.composite
def tournament_rankings(draw: st.DrawFn) -> list[RankedPlayer]:
    """4 to 40 players with distinct league positions, in any order."""
    ids = draw(st.lists(st.uuids(), unique=True, min_size=4, max_size=40))
    positions = draw(
        st.lists(
            st.integers(min_value=1, max_value=200),
            unique=True,
            min_size=len(ids),
            max_size=len(ids),
        )
    )
    return [
        RankedPlayer(
            player_id=PlayerId(i), position=p, is_decided_by_lot=False, tie_group=p
        )
        for i, p in zip(ids, positions, strict=True)
    ]


@given(players=tournament_rankings(), rng_seed=seeds, draw_counter=draw_counters)
def test_br032_halves_cover_every_player_exactly_once(
    players: list[RankedPlayer], rng_seed: bytes, draw_counter: int
) -> None:
    halves = split_halves_by_ranking(
        players, rng_seed=rng_seed, draw_counter=draw_counter
    )

    left_out = () if halves.left_out is None else (halves.left_out,)
    placed = halves.top + halves.bottom + left_out
    assert sorted(placed) == sorted(ranked.player_id for ranked in players)
    assert len(halves.top) == len(halves.bottom) == len(players) // 2
    assert len(left_out) == len(players) % 2


@given(players=tournament_rankings(), rng_seed=seeds, draw_counter=draw_counters)
def test_br032_the_top_half_is_the_better_ranked_half(
    players: list[RankedPlayer], rng_seed: bytes, draw_counter: int
) -> None:
    position = {ranked.player_id: ranked.position for ranked in players}

    halves = split_halves_by_ranking(
        players, rng_seed=rng_seed, draw_counter=draw_counter
    )

    top = [position[player] for player in halves.top]
    bottom = [position[player] for player in halves.bottom]
    assert top == sorted(top)
    assert bottom == sorted(bottom)
    assert max(top) < min(bottom)


@given(players=tournament_rankings(), rng_seed=seeds, draw_counter=draw_counters)
def test_br033_every_player_of_both_halves_is_in_exactly_one_pair(
    players: list[RankedPlayer], rng_seed: bytes, draw_counter: int
) -> None:
    halves = split_halves_by_ranking(
        players, rng_seed=rng_seed, draw_counter=draw_counter
    )

    pairs = draw_partners(halves, rng_seed=rng_seed, draw_counter=draw_counter)

    assert tuple(pair.top for pair in pairs) == tuple(sorted(halves.top))
    assert sorted(pair.bottom for pair in pairs) == sorted(halves.bottom)
    assert all(pair.is_drawn_by_lot for pair in pairs)


@given(
    players=st.lists(
        st.uuids().map(PlayerId), unique=True, min_size=4, max_size=40
    ).map(lambda ids: ids[: len(ids) // 2 * 2]),
    rng_seed=seeds,
    draw_counter=draw_counters,
    data=st.data(),
)
def test_br033_pairs_do_not_depend_on_the_order_of_the_halves(
    players: list[PlayerId], rng_seed: bytes, draw_counter: int, data: st.DataObject
) -> None:
    half = len(players) // 2
    halves = DypHalves(
        top=tuple(players[:half]),
        bottom=tuple(players[half:]),
        left_out=None,
        is_left_out_by_lot=False,
        is_boundary_by_lot=False,
    )
    reordered = replace(
        halves,
        top=tuple(data.draw(st.permutations(halves.top))),
        bottom=tuple(data.draw(st.permutations(halves.bottom))),
    )

    first = draw_partners(halves, rng_seed=rng_seed, draw_counter=draw_counter)
    second = draw_partners(reordered, rng_seed=rng_seed, draw_counter=draw_counter)

    assert first == second


@given(
    sizes=st.tuples(
        st.integers(min_value=0, max_value=12),
        st.integers(min_value=0, max_value=12),
        st.integers(min_value=0, max_value=3),
    ),
)
def test_br032_hand_halves_are_accepted_exactly_when_the_rule_holds(
    sizes: tuple[int, int, int],
) -> None:
    top, bottom, left_out = sizes
    kinds = [DypHalf.TOP] * top + [DypHalf.BOTTOM] * bottom
    kinds += [DypHalf.LEFT_OUT] * left_out
    halves = {pid(n): kind for n, kind in enumerate(kinds, start=1)}
    is_valid = top == bottom and left_out <= 1 and len(kinds) >= 4

    try:
        checked = check_hand_halves(halves)
    except NotEnoughPlayersError, TooManyLeftOutError, DypHalvesUnequalError:
        assert not is_valid
    else:
        assert is_valid
        assert len(checked.top) == len(checked.bottom)
        assert (checked.left_out is not None) == (len(kinds) % 2 == 1)
