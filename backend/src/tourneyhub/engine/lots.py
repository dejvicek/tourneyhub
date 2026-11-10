"""Lots: a stored seed and SHA-256 ordering (ADR-010)."""

from collections.abc import Iterable
from hashlib import sha256
from uuid import UUID

from tourneyhub.engine.ids import ensure_distinct

RNG_SEED_SIZE = 16
"""Bytes in a tournament's `rng_seed`: 128 bits (ADR-010)."""


def lot_digest(*, rng_seed: bytes, purpose: str, candidate: UUID) -> bytes:
    """Return the digest that places `candidate` in the lot named `purpose` (ADR-010).

    The digest is `SHA-256(rng_seed ‖ purpose ‖ id)`: the 16 seed bytes, then
    `purpose` encoded as UTF-8, then the 16 bytes of the candidate's UUID in
    big-endian (RFC 9562) order, with no separators. The seed and the id have
    fixed lengths, so the purpose between them is never ambiguous. Changing
    this layout reorders the lots of every stored tournament.

    Raises:
        ValueError: `rng_seed` is not 16 bytes long.
    """
    if len(rng_seed) != RNG_SEED_SIZE:
        msg = f"rng_seed must be {RNG_SEED_SIZE} bytes, got {len(rng_seed)}"
        raise ValueError(msg)
    return sha256(rng_seed + purpose.encode() + candidate.bytes).digest()


def order_by_lot[I: UUID](
    candidates: Iterable[I], *, rng_seed: bytes, purpose: str
) -> tuple[I, ...]:
    """Order `candidates` by lot (ADR-010; used by BR-020, BR-022, BR-032, BR-033).

    Candidates come out in ascending order of `lot_digest`, compared as bytes.
    The result depends only on the seed, the purpose and the set of
    candidates, never on the order they are given in, and adding or removing
    a candidate does not change the relative order of the others. A random
    draw is this ordering applied to the candidates.

    Raises:
        ValueError: A candidate is given twice, or `rng_seed` is not 16 bytes.
    """
    ids = tuple(candidates)
    ensure_distinct(ids)
    return tuple(
        sorted(
            ids,
            key=lambda candidate: lot_digest(
                rng_seed=rng_seed, purpose=purpose, candidate=candidate
            ),
        )
    )
