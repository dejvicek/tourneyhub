"""Starting a tournament: the entry minimum, the seed order and the round robin.

The round robin is the circle method over the seed order (BR-050 to BR-052). It
draws no lot: the seeds, which setup drew or took from the league ranking, are
its only input (FR-034, ADR-010).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from tourneyhub.engine.errors import NotEnoughEntriesError
from tourneyhub.engine.ids import EntryId, ensure_distinct
from tourneyhub.engine.tournaments import TournamentType

MIN_ENTRIES = 2
"""The fewest entries a tournament starts with (FR-032)."""

MIN_ENTRIES_WITH_THIRD_PLACE = 4
"""The fewest entries of a knockout with a third-place match (FR-032)."""

MIN_MONSTER_DYP_PLAYERS = 4
"""The fewest players of a Monster DYP, whose entries are players (FR-032)."""

MAX_ROUND_ROBIN_ENTRIES = 64
"""The most entries a round robin is generated for.

Everyone plays everyone, so 64 entries are 2,016 matches in one leg and 4,032 in
two. FR-032 caps a round robin at 16 entries (a late entry cannot take it past
16); lowering the limit is the #48 follow-up (issue to open after approval).
"""

ROUND_ROBIN_LEGS = frozenset({1, 2})
"""A round robin is played once or twice (BR-050)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduledMatch:
    """One match of a round, side 1 against side 2.

    Attributes:
        side_1: The entry on side 1.
        side_2: The entry on side 2.
    """

    side_1: EntryId
    side_2: EntryId


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduledRound:
    """One round of a group phase (BR-051).

    Attributes:
        round_no: 1 for the first round; a double round robin continues the
            numbering in its second half (DATA-MODEL §4.5).
        matches: The round's matches in the order they are stored and played
            (BR-130).
        sitting_out: The entry that sits the round out with an odd number of
            entries, otherwise None.
    """

    round_no: int
    matches: tuple[ScheduledMatch, ...]
    sitting_out: EntryId | None


def minimum_entries(*, tournament_type: TournamentType, third_place_match: bool) -> int:
    """Return how many entries a tournament needs to start (FR-032).

    At least 2, or 4 with a third-place match; a Monster DYP needs 4 players,
    and each of its players is an entry.
    """
    if tournament_type is TournamentType.MONSTER_DYP:
        return MIN_MONSTER_DYP_PLAYERS
    return MIN_ENTRIES_WITH_THIRD_PLACE if third_place_match else MIN_ENTRIES


def check_entry_count(
    *, tournament_type: TournamentType, third_place_match: bool, given: int
) -> None:
    """Refuse a start with too few entries (FR-032).

    Raises:
        NotEnoughEntriesError: Fewer entries than `minimum_entries` returns.
    """
    minimum = minimum_entries(
        tournament_type=tournament_type, third_place_match=third_place_match
    )
    if given < minimum:
        raise NotEnoughEntriesError(minimum=minimum, given=given)


def seed_order(seeds: Iterable[tuple[EntryId, int | None]]) -> tuple[EntryId, ...]:
    """Return the entries by seed, seed 1 first (FR-034).

    Setup seeds every entry whenever the entries change, so a missing or
    repeated seed is a caller bug, not an organizer's.

    Raises:
        ValueError: An entry is given twice, has no seed, or the seeds are not
            exactly 1 to the number of entries.
    """
    pairs = tuple(seeds)
    ensure_distinct(entry_id for entry_id, _ in pairs)
    by_seed: dict[int, EntryId] = {}
    for entry_id, seed in pairs:
        if seed is None:
            msg = f"entry {entry_id} has no seed"
            raise ValueError(msg)
        by_seed[seed] = entry_id
    if sorted(by_seed) != list(range(1, len(pairs) + 1)):
        msg = f"the seeds {sorted(by_seed)} are not 1 to {len(pairs)}"
        raise ValueError(msg)
    return tuple(by_seed[seed] for seed in sorted(by_seed))


def round_robin(entries: Sequence[EntryId], *, legs: int) -> tuple[ScheduledRound, ...]:
    """Schedule a round robin by the circle method (BR-050 to BR-052).

    `entries` come in seed order. With an odd number, an empty slot joins
    them, and the entry drawn against it sits the round out, so each entry
    sits out once per leg (BR-051). Seed 1 keeps its slot while the others
    turn one step each round; round 1 pairs the first seed with the last,
    the second with the second last, and so on (8 entries: 1 v 8, 2 v 7,
    3 v 6, 4 v 5). The lower slot is side 1.

    A second leg repeats the first leg's rounds in order with the sides
    swapped (BR-052), numbered on from the first leg, so every two entries
    meet once on each side.

    Returns:
        The rounds, round 1 first: `legs * (n - 1)` rounds of `n / 2` matches
        for an even number `n` of entries, `legs * n` rounds of `(n - 1) / 2`
        matches for an odd one.

    Raises:
        ValueError: `legs` is not 1 or 2, there are fewer than 2 entries, or an
            entry is given twice.
    """
    if legs not in ROUND_ROBIN_LEGS:
        msg = f"a round robin is played once or twice, not {legs} times"
        raise ValueError(msg)
    ensure_distinct(entries)
    if len(entries) < MIN_ENTRIES:
        msg = f"a round robin needs {MIN_ENTRIES} entries, got {len(entries)}"
        raise ValueError(msg)
    slots: list[EntryId | None] = list(entries)
    if len(slots) % 2:
        slots.append(None)
    fixed, rest = slots[0], slots[1:]
    first_leg: list[ScheduledRound] = []
    for index in range(len(rest)):
        turned = rest[len(rest) - index :] + rest[: len(rest) - index]
        line = [fixed, *turned]
        matches: list[ScheduledMatch] = []
        sitting_out: EntryId | None = None
        for slot in range(len(line) // 2):
            side_1, side_2 = line[slot], line[-1 - slot]
            if side_2 is None:
                sitting_out = side_1
            elif side_1 is None:
                sitting_out = side_2
            else:
                matches.append(ScheduledMatch(side_1=side_1, side_2=side_2))
        first_leg.append(
            ScheduledRound(
                round_no=index + 1, matches=tuple(matches), sitting_out=sitting_out
            )
        )
    second_leg = (
        ScheduledRound(
            round_no=round_.round_no + len(first_leg),
            matches=tuple(
                ScheduledMatch(side_1=match.side_2, side_2=match.side_1)
                for match in round_.matches
            ),
            sitting_out=round_.sitting_out,
        )
        for round_ in first_leg
        if legs == 2  # noqa: PLR2004  (the second leg, BR-052)
    )
    return (*first_leg, *second_leg)
