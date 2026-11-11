from functools import cache
from itertools import combinations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tourneyhub.engine.blossom import Pair, maximum_matching


def brute_force_size(count: int, edges: frozenset[Pair]) -> int:
    """The size of a maximum matching, by trying every choice (an oracle)."""

    @cache
    def best(free: frozenset[int]) -> int:
        if not free:
            return 0
        node = min(free)
        rest = free - {node}
        matched = (
            1 + best(rest - {other})
            for other in rest
            if (min(node, other), max(node, other)) in edges
        )
        return max([best(rest), *matched])  # `node` unmatched, or matched

    return best(frozenset(range(count)))


@st.composite
def graphs(draw: st.DrawFn) -> tuple[int, list[Pair]]:
    count = draw(st.integers(min_value=0, max_value=10))
    possible = list(combinations(range(count), 2))
    edges = draw(st.lists(st.sampled_from(possible), unique=True)) if possible else []
    return count, edges


def test_an_empty_graph_has_no_pairs() -> None:
    assert maximum_matching(3, []) == ()


def test_a_path_is_matched_from_the_lowest_node() -> None:
    assert maximum_matching(4, [(0, 1), (1, 2), (2, 3)]) == ((0, 1), (2, 3))


def test_an_initial_matching_grows_along_an_augmenting_path() -> None:
    result = maximum_matching(4, [(0, 1), (1, 2), (2, 3)], initial=[(1, 2)])

    assert result == ((0, 1), (2, 3))


def test_a_blossom_is_shrunk_to_reach_a_free_node() -> None:
    # The odd cycle 0-1-2-3-4 hides the free node 5 behind 3 (Edmonds).
    cycle = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)]

    result = maximum_matching(6, [*cycle, (3, 5)], initial=[(1, 2), (3, 4)])

    assert len(result) == 3


def test_a_node_reached_twice_is_not_relabelled() -> None:
    # 0 reaches 1 and 3; 1's mate 2 reaches 3 again, already an odd node.
    edges = [(0, 1), (1, 2), (2, 3), (0, 3)]

    result = maximum_matching(5, edges, initial=[(1, 2)])

    assert len(result) == 2


def test_an_odd_cycle_leaves_one_node_free() -> None:
    assert maximum_matching(3, [(0, 1), (1, 2), (0, 2)]) == ((0, 1),)


def test_a_repeated_edge_counts_once() -> None:
    assert maximum_matching(2, [(0, 1), (1, 0)]) == ((0, 1),)


@pytest.mark.parametrize(
    ("count", "edges", "initial"),
    [
        pytest.param(2, [(0, 0)], [], id="self-loop"),
        pytest.param(2, [(0, 2)], [], id="unknown-node"),
        pytest.param(2, [(-1, 0)], [], id="negative-node"),
        pytest.param(3, [(0, 1)], [(1, 2)], id="initial-not-an-edge"),
        pytest.param(3, [(0, 1), (1, 2)], [(0, 1), (1, 2)], id="initial-reuses"),
    ],
)
def test_a_caller_bug_raises(
    count: int, edges: list[Pair], initial: list[Pair]
) -> None:
    with pytest.raises(ValueError, match=r"edge|initial"):
        maximum_matching(count, edges, initial=initial)


@given(graphs())
def test_the_matching_is_maximum(graph: tuple[int, list[Pair]]) -> None:
    count, edges = graph

    result = maximum_matching(count, edges)

    assert set(result) <= set(edges)
    assert len({node for pair in result for node in pair}) == 2 * len(result)
    assert len(result) == brute_force_size(count, frozenset(edges))


@given(graphs(), st.data())
def test_any_initial_matching_grows_to_a_maximum(
    graph: tuple[int, list[Pair]], data: st.DataObject
) -> None:
    count, edges = graph
    initial: list[Pair] = []
    for u, v in data.draw(st.permutations(edges)):
        if all(u not in pair and v not in pair for pair in initial):
            initial.append((u, v))

    result = maximum_matching(count, edges, initial=initial)

    assert len(result) == brute_force_size(count, frozenset(edges))
