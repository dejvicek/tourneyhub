"""Seeding in setup: by league ranking or by random shuffle (BR-021, BR-022)."""

from collections.abc import Iterable
from dataclasses import dataclass

from tourneyhub.engine.ids import EntryId, PlayerId, ensure_distinct
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.ranking import RankedPlayer


@dataclass(frozen=True, slots=True, kw_only=True)
class SeedingEntry:
    """An entry to seed: one player in Singles, two in Doubles and DYP (BR-030).

    Attributes:
        entry_id: The entry.
        player_ids: The entry's one or two players.
    """

    entry_id: EntryId
    player_ids: tuple[PlayerId, ...]


def shuffle_purpose(draw_counter: int) -> str:
    """Name the lot of a random shuffle, `shuffle:<draw_counter>` (BR-022, ADR-010)."""
    return f"shuffle:{draw_counter}"


def seed_by_ranking(
    entries: Iterable[SeedingEntry], ranking: Iterable[RankedPlayer]
) -> tuple[EntryId, ...]:
    """Seed the entries by league ranking (BR-021).

    Each entry scores the sum of its players' positions in `ranking`, lowest
    first, so a single player follows the ranking. On equal sums, the entry
    with the better-ranked player goes first. Two valid entries never tie
    after that, since no player is in two entries (BR-003).

    `ranking` is the league ranking of every player of the league (BR-020),
    so the positions are league positions, not positions among the entries.

    Returns:
        The entry ids, seed 1 first.

    Raises:
        ValueError: An entry has no player or more than two, a player is in
            two entries or twice in one (BR-003, BR-030), or an entry's player
            is not in `ranking`.
    """
    entries = tuple(entries)
    for entry in entries:
        if len(entry.player_ids) not in {1, 2}:
            msg = f"entry {entry.entry_id} has {len(entry.player_ids)} players"
            raise ValueError(msg)
    ensure_distinct(player_id for entry in entries for player_id in entry.player_ids)
    positions = {ranked.player_id: ranked.position for ranked in ranking}

    def key(entry: SeedingEntry) -> tuple[int, int]:
        try:
            members = [positions[player_id] for player_id in entry.player_ids]
        except KeyError as err:
            msg = f"player {err.args[0]} is not in the ranking"
            raise ValueError(msg) from err
        return sum(members), min(members)

    return tuple(entry.entry_id for entry in sorted(entries, key=key))


def seed_by_lot(
    entry_ids: Iterable[EntryId], *, rng_seed: bytes, draw_counter: int
) -> tuple[EntryId, ...]:
    """Seed the entries by random shuffle: the order of a lot (BR-022, ADR-010).

    The lot's purpose is `shuffle:<draw_counter>`, so "shuffle again", which
    increments the tournament's draw counter, draws a new order that can
    still be recomputed.

    Returns:
        The entry ids, seed 1 first.
    """
    return order_by_lot(
        entry_ids, rng_seed=rng_seed, purpose=shuffle_purpose(draw_counter)
    )
