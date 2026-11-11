from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.matching import min_cost_matching


def test_adr011_finds_the_cheapest_perfect_matching() -> None:
    edges = [(0, 1, 1), (2, 3, 1), (0, 2, 4), (1, 3, 4), (0, 3, 9), (1, 2, 1)]

    pairs = min_cost_matching(4, edges)

    assert pairs == ((0, 1), (2, 3))


def test_adr011_prefers_more_pairs_to_cheaper_ones() -> None:
    edges = [(0, 1, 1), (1, 2, 100), (0, 3, 100)]

    pairs = min_cost_matching(4, edges)

    assert pairs == ((0, 3), (1, 2))


def test_adr011_without_a_perfect_matching_returns_fewer_pairs() -> None:
    edges = [(0, 1, 1), (0, 2, 1), (0, 3, 1)]

    pairs = min_cost_matching(4, edges)

    assert len(pairs) == 1


def test_adr011_puts_the_lower_node_first() -> None:
    pairs = min_cost_matching(2, [(1, 0, 5)])

    assert pairs == ((0, 1),)


@given(st.integers(min_value=0, max_value=12).map(lambda half: 2 * half))
def test_adr011_a_complete_graph_pairs_neighbours(count: int) -> None:
    edges = [
        (top, bottom, (bottom - top) ** 2)
        for top in range(count)
        for bottom in range(top + 1, count)
    ]

    pairs = min_cost_matching(count, edges)

    assert pairs == tuple((top, top + 1) for top in range(0, count, 2))
