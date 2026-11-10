from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.lots import lot_digest, order_by_lot

SEED = bytes(range(16))

seeds = st.binary(min_size=16, max_size=16)
purposes = st.text(max_size=30)
candidate_sets = st.lists(st.uuids(), unique=True, max_size=40)


def test_adr010_pins_the_digest_layout() -> None:
    # Computed outside Python: printf the seed, purpose and id bytes | shasum -a 256
    candidate = UUID("0192e2b0-a1b2-7c3d-8e4f-5a6b7c8d9e0f")

    digest = lot_digest(rng_seed=SEED, purpose="dyp-partner:2", candidate=candidate)

    assert digest.hex() == (
        "5d61894424a2735eef383216ae4c9d74ba5e3e5fafc908c829900ec5f6f1cba2"
    )


def test_adr010_pins_one_ordering() -> None:
    candidates = [UUID(int=n) for n in range(1, 6)]

    ordered = order_by_lot(candidates, rng_seed=SEED, purpose="shuffle:0")

    # Also computed outside Python, by sorting the five shasum digests
    assert [candidate.int for candidate in ordered] == [3, 1, 5, 4, 2]


def test_adr010_orders_by_ascending_digest() -> None:
    candidates = [UUID(int=n) for n in range(10)]

    ordered = order_by_lot(candidates, rng_seed=SEED, purpose="tiebreak")

    digests = [
        lot_digest(rng_seed=SEED, purpose="tiebreak", candidate=c) for c in ordered
    ]
    assert digests == sorted(digests)


@pytest.mark.parametrize(
    "size", [pytest.param(15, id="short"), pytest.param(17, id="long")]
)
def test_adr010_refuses_a_seed_that_is_not_128_bits(size: int) -> None:
    with pytest.raises(ValueError, match="rng_seed"):
        lot_digest(rng_seed=bytes(size), purpose="tiebreak", candidate=UUID(int=1))


def test_adr010_refuses_a_candidate_given_twice() -> None:
    with pytest.raises(ValueError, match="twice"):
        order_by_lot([UUID(int=1), UUID(int=1)], rng_seed=SEED, purpose="tiebreak")


@given(candidates=candidate_sets, rng_seed=seeds, purpose=purposes)
def test_adr010_lot_is_a_permutation(
    candidates: list[UUID], rng_seed: bytes, purpose: str
) -> None:
    ordered = order_by_lot(candidates, rng_seed=rng_seed, purpose=purpose)

    assert sorted(ordered) == sorted(candidates)


@given(candidates=candidate_sets, rng_seed=seeds, purpose=purposes, data=st.data())
def test_adr010_lot_is_deterministic_whatever_the_input_order(
    candidates: list[UUID], rng_seed: bytes, purpose: str, data: st.DataObject
) -> None:
    reordered = data.draw(st.permutations(candidates))

    first = order_by_lot(candidates, rng_seed=rng_seed, purpose=purpose)
    second = order_by_lot(reordered, rng_seed=rng_seed, purpose=purpose)

    assert first == second


@given(candidates=candidate_sets, rng_seed=seeds, purpose=purposes, data=st.data())
def test_adr010_other_candidates_keep_their_relative_order(
    candidates: list[UUID], rng_seed: bytes, purpose: str, data: st.DataObject
) -> None:
    subset = [c for c in candidates if data.draw(st.booleans())]

    full = order_by_lot(candidates, rng_seed=rng_seed, purpose=purpose)
    partial = order_by_lot(subset, rng_seed=rng_seed, purpose=purpose)

    assert partial == tuple(c for c in full if c in subset)


@given(
    candidates=st.lists(st.uuids(), unique=True, min_size=12, max_size=40),
    rng_seed=seeds,
    purposes=st.lists(purposes, unique=True, min_size=2, max_size=2),
)
def test_adr010_purposes_draw_independent_orders(
    candidates: list[UUID], rng_seed: bytes, purposes: list[str]
) -> None:
    # Two orders of 12 or more candidates agree by chance with odds below 1 in
    # 479 million, so equal orders would mean the purpose is ignored.
    first, second = (
        order_by_lot(candidates, rng_seed=rng_seed, purpose=purpose)
        for purpose in purposes
    )

    assert first != second


@given(
    candidates=st.lists(st.uuids(), unique=True, min_size=12, max_size=40),
    rng_seeds=st.lists(seeds, unique=True, min_size=2, max_size=2),
    purpose=purposes,
)
def test_adr010_seeds_draw_independent_orders(
    candidates: list[UUID], rng_seeds: list[bytes], purpose: str
) -> None:
    first, second = (
        order_by_lot(candidates, rng_seed=rng_seed, purpose=purpose)
        for rng_seed in rng_seeds
    )

    assert first != second
