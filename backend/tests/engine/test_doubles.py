from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.doubles import pair_purpose, pair_the_rest
from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.lots import order_by_lot

SEED = bytes(range(16))


def pid(n: int) -> PlayerId:
    return PlayerId(UUID(int=n))


def test_fr033_pairs_follow_the_lot_two_by_two() -> None:
    players = [pid(n) for n in range(1, 7)]
    drawn = order_by_lot(players, rng_seed=SEED, purpose="doubles-pair:3")

    pairs = pair_the_rest(players, rng_seed=SEED, draw_counter=3)

    assert pairs == ((drawn[0], drawn[1]), (drawn[2], drawn[3]), (drawn[4], drawn[5]))


def test_fr033_with_an_odd_number_the_last_of_the_lot_stays_alone() -> None:
    players = [pid(n) for n in range(1, 6)]
    drawn = order_by_lot(players, rng_seed=SEED, purpose=pair_purpose(1))

    pairs = pair_the_rest(players, rng_seed=SEED, draw_counter=1)

    assert len(pairs) == 2
    assert drawn[4] not in {player for pair in pairs for player in pair}


def test_adr010_another_draw_counter_draws_other_pairs() -> None:
    players = [pid(n) for n in range(1, 9)]

    draws = {pair_the_rest(players, rng_seed=SEED, draw_counter=n) for n in range(5)}

    assert len(draws) > 1


def test_adr010_a_player_given_twice_is_a_caller_bug() -> None:
    with pytest.raises(ValueError, match="given twice"):
        pair_the_rest([pid(1), pid(1)], rng_seed=SEED, draw_counter=0)


@given(st.sets(st.integers(min_value=1, max_value=10_000), max_size=40))
def test_br030_every_pair_has_two_different_players_each_once(ids: set[int]) -> None:
    pairs = pair_the_rest(map(pid, ids), rng_seed=SEED, draw_counter=0)

    paired = [player for pair in pairs for player in pair]
    assert len(set(paired)) == len(paired) == len(ids) - len(ids) % 2
