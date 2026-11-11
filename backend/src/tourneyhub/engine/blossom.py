"""Maximum-cardinality matching in a general graph (Edmonds' blossom algorithm).

Monster DYP uses it to tell whether a repeated partner can be avoided, and to
avoid it when the swaps of ADR-011 cannot (BR-062). It is plain Python, so it
needs no dependency.
"""

from collections.abc import Iterable, Sequence

type Pair = tuple[int, int]
"""Two node numbers, the lower first."""

_UNMATCHED = -1


def maximum_matching(
    count: int, edges: Iterable[Pair], *, initial: Iterable[Pair] = ()
) -> tuple[Pair, ...]:
    """Return a matching of nodes `0` to `count - 1` with as many pairs as possible.

    The search starts from `initial` and grows it one augmenting path at a
    time, so a pair of `initial` changes only where a larger matching needs
    it. Free nodes are tried in ascending order and neighbours in the order
    of `edges`, so the result is the same on every call.

    Args:
        count: The number of nodes.
        edges: The pairs that may be matched; a repeated edge counts once.
        initial: A matching to start from, made of given edges.

    Returns:
        The pairs, each with the lower node first, in ascending order.

    Raises:
        ValueError: An edge joins a node to itself or names a node outside
            `0` to `count - 1`, or `initial` uses a node twice or a pair that
            is not an edge.
    """
    adjacent: list[list[int]] = [[] for _ in range(count)]
    known: set[Pair] = set()
    for u, v in edges:
        if u == v or not (0 <= u < count and 0 <= v < count):
            msg = f"edge ({u}, {v}) is not between two of {count} nodes"
            raise ValueError(msg)
        if (min(u, v), max(u, v)) not in known:
            known.add((min(u, v), max(u, v)))
            adjacent[u].append(v)
            adjacent[v].append(u)
    mate = [_UNMATCHED] * count
    for u, v in initial:
        if (min(u, v), max(u, v)) not in known:
            msg = f"initial pair ({u}, {v}) is not an edge"
            raise ValueError(msg)
        if mate[u] != _UNMATCHED or mate[v] != _UNMATCHED:
            msg = f"initial pair ({u}, {v}) reuses a node"
            raise ValueError(msg)
        mate[u], mate[v] = v, u
    for root in range(count):
        if mate[root] == _UNMATCHED:
            _augment_from(root, adjacent, mate)
    return tuple((node, mate[node]) for node in range(count) if node < mate[node])


def _augment_from(
    root: int, adjacent: Sequence[Sequence[int]], mate: list[int]
) -> None:
    """Grow the matching along an augmenting path from the free node `root`, if any.

    A breadth-first search over alternating paths that shrinks each odd cycle
    (a blossom) to its base. By Edmonds' theorem a node without an augmenting
    path never gets one later, so one pass over the free nodes is enough.
    """
    count = len(mate)
    parent = [_UNMATCHED] * count
    base = list(range(count))
    in_tree = [False] * count
    in_tree[root] = True
    queue = [root]

    def common_base(a: int, b: int) -> int:
        on_path = [False] * count
        while True:
            a = base[a]
            on_path[a] = True
            if mate[a] == _UNMATCHED:
                break
            a = parent[mate[a]]
        while not on_path[base[b]]:
            b = parent[mate[base[b]]]
        return base[b]

    def mark_path(node: int, stem: int, child: int, blossom: list[bool]) -> None:
        while base[node] != stem:
            blossom[base[node]] = blossom[base[mate[node]]] = True
            parent[node] = child
            child = mate[node]
            node = parent[mate[node]]

    head = 0
    while head < len(queue):
        node = queue[head]
        head += 1
        for other in adjacent[node]:
            if base[node] == base[other] or mate[node] == other:
                continue
            if other == root or (
                mate[other] != _UNMATCHED and parent[mate[other]] != _UNMATCHED
            ):
                stem = common_base(node, other)
                blossom = [False] * count
                mark_path(node, stem, other, blossom)
                mark_path(other, stem, node, blossom)
                for member in range(count):
                    if blossom[base[member]]:
                        base[member] = stem
                        if not in_tree[member]:
                            in_tree[member] = True
                            queue.append(member)
            elif parent[other] == _UNMATCHED:
                parent[other] = node
                if mate[other] == _UNMATCHED:
                    _flip(other, parent, mate)
                    return
                in_tree[mate[other]] = True
                queue.append(mate[other])


def _flip(end: int, parent: Sequence[int], mate: list[int]) -> None:
    """Swap matched and unmatched edges along the path that ends at `end`."""
    while end != _UNMATCHED:
        previous = parent[end]
        following = mate[previous]
        mate[end], mate[previous] = previous, end
        end = following
