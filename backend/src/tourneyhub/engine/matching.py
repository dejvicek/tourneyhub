"""Minimum-cost matching, the fallback for pairing a round (ADR-011)."""

from collections.abc import Iterable

import networkx as nx

type Pair = tuple[int, int]
"""Two node numbers, the lower first."""


def min_cost_matching(
    count: int, edges: Iterable[tuple[int, int, int]]
) -> tuple[Pair, ...]:
    """Return the cheapest of the largest matchings of nodes `0` to `count - 1`.

    `edges` are `(u, v, cost)` triples with whole-number costs; a pair
    without an edge is never matched. The blossom algorithm
    (`networkx.min_weight_matching`) finds the cheapest matching among those
    with the most pairs (ADR-011), so the result is a perfect matching, with
    `count / 2` pairs, exactly when one exists. The graph is built in the
    order the edges come in, which makes the choice between equally cheap
    matchings the same on every call.

    Returns:
        The pairs, each with the lower node first, in ascending order.
    """
    # The data types are spelled out: the stub defaults them to dict[str, Any].
    graph: nx.Graph[int, dict[str, object], dict[str, object]] = nx.Graph()
    graph.add_nodes_from(range(count))
    graph.add_weighted_edges_from(edges)
    return tuple(
        sorted((min(u, v), max(u, v)) for u, v in nx.min_weight_matching(graph))
    )
