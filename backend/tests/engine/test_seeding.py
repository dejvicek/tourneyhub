from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.ids import EntryId, PlayerId
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.ranking import RankedPlayer
from tourneyhub.engine.seeding import SeedingEntry, seed_by_lot, seed_by_ranking

SEED = bytes(range(16))


def ranked(position: int) -> RankedPlayer:
    """The player at `position`, whose id is that position."""
    return RankedPlayer(
        player_id=PlayerId(UUID(int=position)),
        position=position,
        is_decided_by_lot=False,
        tie_group=position,
    )


def entry(n: int, *positions: int) -> SeedingEntry:
    return SeedingEntry(
        entry_id=EntryId(UUID(int=1000 + n)),
        player_ids=tuple(PlayerId(UUID(int=p)) for p in positions),
    )


def numbers(entry_ids: tuple[EntryId, ...]) -> list[int]:
    return [entry_id.int - 1000 for entry_id in entry_ids]


LEAGUE = [ranked(position) for position in range(1, 21)]


def test_br021_singles_follow_the_ranking() -> None:
    entries = [entry(1, 7), entry(2, 2), entry(3, 15), entry(4, 4)]

    seeds = seed_by_ranking(entries, LEAGUE)

    assert numbers(seeds) == [2, 4, 1, 3]


def test_br021_orders_pairs_by_the_sum_of_their_positions() -> None:
    entries = [entry(1, 1, 12), entry(2, 3, 4), entry(3, 2, 9)]

    seeds = seed_by_ranking(entries, LEAGUE)

    assert numbers(seeds) == [2, 3, 1]  # sums 7, 11, 13


def test_br021_on_equal_sums_the_pair_with_the_better_ranked_player_goes_first() -> (
    None
):
    entries = [entry(1, 4, 5), entry(2, 2, 7), entry(3, 3, 6)]

    seeds = seed_by_ranking(entries, LEAGUE)

    assert numbers(seeds) == [2, 3, 1]  # all sum to 9


def test_br021_uses_league_positions_not_positions_among_the_entries() -> None:
    # Among these four players alone, both pairs would sum to 5 and #1's pair
    # would go first; in the league ranking, 5 + 6 = 11 beats 1 + 20 = 21.
    entries = [entry(1, 1, 20), entry(2, 5, 6)]

    seeds = seed_by_ranking(entries, LEAGUE)

    assert numbers(seeds) == [2, 1]


def test_br021_refuses_a_player_missing_from_the_ranking() -> None:
    with pytest.raises(ValueError, match="not in the ranking"):
        seed_by_ranking([entry(1, 21)], LEAGUE)


@pytest.mark.parametrize(
    "positions",
    [pytest.param((), id="no-player"), pytest.param((1, 2, 3), id="three-players")],
)
def test_br030_refuses_an_entry_that_is_not_a_player_or_a_pair(
    positions: tuple[int, ...],
) -> None:
    with pytest.raises(ValueError, match="players"):
        seed_by_ranking([entry(1, *positions)], LEAGUE)


def test_br003_refuses_a_player_in_two_entries() -> None:
    with pytest.raises(ValueError, match="twice"):
        seed_by_ranking([entry(1, 1, 2), entry(2, 2, 3)], LEAGUE)


def test_br022_shuffle_orders_the_entries_by_lot() -> None:
    entry_ids = [EntryId(UUID(int=1000 + n)) for n in range(1, 9)]

    seeds = seed_by_lot(entry_ids, rng_seed=SEED, draw_counter=3)

    assert seeds == order_by_lot(entry_ids, rng_seed=SEED, purpose="shuffle:3")


def test_br022_shuffle_again_draws_with_the_next_counter() -> None:
    entry_ids = [EntryId(UUID(int=1000 + n)) for n in range(1, 13)]

    first = seed_by_lot(entry_ids, rng_seed=SEED, draw_counter=0)
    again = seed_by_lot(entry_ids, rng_seed=SEED, draw_counter=1)

    assert first != again
    assert sorted(first) == sorted(again)


@given(positions=st.permutations(range(1, 21)), data=st.data())
def test_br021_pair_seeding_is_ordered_by_sum_then_best_position(
    positions: list[int], data: st.DataObject
) -> None:
    count = data.draw(st.integers(min_value=0, max_value=10))
    entries = [entry(n, positions[2 * n], positions[2 * n + 1]) for n in range(count)]
    by_id = {e.entry_id: e for e in entries}

    seeds = seed_by_ranking(entries, LEAGUE)

    assert sorted(seeds) == sorted(by_id)
    keys = [
        (
            sum(p.int for p in by_id[s].player_ids),
            min(p.int for p in by_id[s].player_ids),
        )
        for s in seeds
    ]
    assert keys == sorted(keys)
