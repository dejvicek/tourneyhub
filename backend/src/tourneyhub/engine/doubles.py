"""Doubles pairs: the organizer pairs the players, a lot pairs the rest (FR-033)."""

from collections.abc import Iterable

from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.lots import order_by_lot


def pair_purpose(draw_counter: int) -> str:
    """Name the lot that pairs the rest, `doubles-pair:<draw_counter>` (ADR-010)."""
    return f"doubles-pair:{draw_counter}"


def pair_the_rest(
    players: Iterable[PlayerId], *, rng_seed: bytes, draw_counter: int
) -> tuple[tuple[PlayerId, PlayerId], ...]:
    """Pair players without a partner at random (FR-033, BR-030, ADR-010).

    The players are ordered by the lot `doubles-pair:<draw_counter>`, and each
    two in that order form a pair. With an odd number, the last player of the
    lot stays without a partner: Doubles has no rule that leaves a player out,
    so the organizer decides.

    Returns:
        The pairs, in the lot's order.

    Raises:
        ValueError: A player is given twice, or `rng_seed` is not 16 bytes.
    """
    drawn = order_by_lot(players, rng_seed=rng_seed, purpose=pair_purpose(draw_counter))
    return tuple(zip(drawn[0::2], drawn[1::2], strict=False))
