"""The knockout: the cut, the bracket, the sides derived from winners and the lock.

A knockout is single elimination (glossary "Knockout"). Its matches are all
created when it is drawn, but only the first round's sides are stored; every
later side, the third-place match's included, is derived here from the first
round and the stored winners (DATA-MODEL D4). Nothing is cascaded when a result
changes: BR-094 refuses a change while a later match it feeds has a result, so
a stored result always refers to the sides derived for it.

BR-040 to BR-044, BR-074, BR-080, BR-085, BR-094, BR-102.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from tourneyhub.engine.errors import QualifierCountError
from tourneyhub.engine.ids import EntryId, ensure_distinct
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.places import KnockoutResult
from tourneyhub.engine.tournaments import MatchKind, Outcome

MIN_KNOCKOUT_ENTRIES = 2
"""The fewest entries of a knockout (BR-080)."""

MIN_KNOCKOUT_ENTRIES_WITH_THIRD_PLACE = 4
"""The fewest entries of a knockout with a third-place match (BR-080)."""

KNOCKOUT_SEEDING_PURPOSE = "knockout-seeding"
"""The lot that orders entries still level for the knockout's cut and seeding.

BR-074 and ADR-010. The knockout's entries and seeds are stored when it is
drawn, so the lot runs once per draw. The purpose holds no counter: deleting
the knockout and drawing it again from the same standings gives the same
seeds, which is what a redraw of an unchanged group phase should give.
"""


class RoundName(StrEnum):
    """What a bracket round is called, by the entries still in it."""

    FINAL = "final"
    SEMIFINAL = "semifinal"
    QUARTERFINAL = "quarterfinal"
    ROUND_OF_16 = "round_of_16"
    ROUND_OF_32 = "round_of_32"
    ROUND_OF_64 = "round_of_64"
    ROUND_OF_128 = "round_of_128"
    ROUND_OF_256 = "round_of_256"


def minimum_qualifiers(*, third_place_match: bool) -> int:
    """The fewest entries a knockout needs: 2, or 4 with a third-place match (BR-080)."""
    return (
        MIN_KNOCKOUT_ENTRIES_WITH_THIRD_PLACE
        if third_place_match
        else MIN_KNOCKOUT_ENTRIES
    )


def bracket_size(entry_count: int) -> int:
    """The smallest power of two that fits the entries: 7 entries, 8 (BR-040).

    Raises:
        ValueError: Fewer than 2 entries.
    """
    if entry_count < MIN_KNOCKOUT_ENTRIES:
        msg = f"a knockout needs {MIN_KNOCKOUT_ENTRIES} entries, got {entry_count}"
        raise ValueError(msg)
    return 1 << (entry_count - 1).bit_length()


def seed_slots(size: int) -> tuple[int, ...]:
    """The seeds in bracket order, top of the bracket first (BR-042).

    Round 1 pairs neighbouring slots: with 8, `1 8 4 5 2 7 3 6` gives 1 v 8,
    4 v 5, 2 v 7 and 3 v 6. Each step doubles the bracket and puts against
    every seed s the seed `2n + 1 - s`, so seeds 1 and 2 are in different
    halves and meet only in the final, and seeds 1 to 4 in different quarters
    and meet only in the semifinals or later.

    Raises:
        ValueError: `size` is not a power of two of at least 2.
    """
    if size < MIN_KNOCKOUT_ENTRIES or size & (size - 1):
        msg = f"a bracket's size is a power of two of at least 2, not {size}"
        raise ValueError(msg)
    order = [1]
    while len(order) < size:
        doubled = 2 * len(order)
        order = [slot for seed in order for slot in (seed, doubled + 1 - seed)]
    return tuple(order)


def round_name(round_no: int, round_count: int) -> RoundName:
    """The name of round `round_no` of `round_count`: the last is the final.

    Raises:
        ValueError: `round_no` is not 1 to `round_count`, or the round would
            have more than 256 entries (FR-032).
    """
    if not 1 <= round_no <= round_count:
        msg = f"round {round_no} is not a round of {round_count}"
        raise ValueError(msg)
    entries = 2 ** (round_count - round_no + 1)
    names = {
        2: RoundName.FINAL,
        4: RoundName.SEMIFINAL,
        8: RoundName.QUARTERFINAL,
    }
    if entries in names:
        return names[entries]
    return RoundName(f"round_of_{entries}")


@dataclass(frozen=True, slots=True, order=True, kw_only=True)
class MatchKey:
    """Where a match sits in the bracket (DATA-MODEL `matches`).

    Attributes:
        round_no: 1 for the first round; the final's round is the last.
        is_third_place: The third-place match, which sits in the final's round
            after the final (BR-044, BR-130).
        position: The match's slot within its round, top of the bracket first;
            the third-place match is 1.
    """

    round_no: int
    is_third_place: bool
    position: int

    @property
    def kind(self) -> MatchKind:
        """The stored kind: standard, or the third-place match."""
        return MatchKind.THIRD_PLACE if self.is_third_place else MatchKind.STANDARD


def match_key(*, round_no: int, kind: MatchKind, position: int) -> MatchKey:
    """The key of a stored match, from its round, kind and position."""
    return MatchKey(
        round_no=round_no,
        is_third_place=kind is MatchKind.THIRD_PLACE,
        position=position,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Side:
    """One side of a bracket match.

    Attributes:
        entry_id: The entry, once known; None for a bye or a side that waits
            for an earlier match.
        is_bye: An empty spot of the first round (BR-041).
    """

    entry_id: EntryId | None
    is_bye: bool = False

    @property
    def is_known(self) -> bool:
        """The side is an entry or a bye, not a winner still to come."""
        return self.is_bye or self.entry_id is not None


_UNKNOWN = Side(entry_id=None)
_BYE = Side(entry_id=None, is_bye=True)


@dataclass(frozen=True, slots=True, kw_only=True)
class FirstRoundMatch:
    """A first-round match as it is stored: two entries, or an entry and a bye.

    Attributes:
        position: The match's slot, 1 at the top of the bracket.
        side_1: The entry on side 1, or None for a bye.
        side_2: The entry on side 2, or None for a bye.
    """

    position: int
    side_1: EntryId | None
    side_2: EntryId | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Bracket:
    """The shape of a knockout and its first round (BR-040, BR-041).

    Attributes:
        size: The number of first-round spots, a power of two.
        third_place_match: The semifinal losers play for 3rd (BR-044).
        first_round: The `size / 2` first-round matches, by position.
    """

    size: int
    third_place_match: bool
    first_round: tuple[FirstRoundMatch, ...]

    @property
    def round_count(self) -> int:
        """The number of rounds; the last holds the final."""
        return self.size.bit_length() - 1

    @property
    def keys(self) -> tuple[MatchKey, ...]:
        """Every match, byes included, in schedule order (BR-130).

        By round, top of the bracket first; the third-place match after the
        final.
        """
        keys = [
            MatchKey(round_no=round_no, is_third_place=False, position=position)
            for round_no in range(1, self.round_count + 1)
            for position in range(1, (self.size >> round_no) + 1)
        ]
        if self.third_place_match:
            keys.append(
                MatchKey(round_no=self.round_count, is_third_place=True, position=1)
            )
        return tuple(keys)

    @property
    def final(self) -> MatchKey:
        """The final: the standard match of the last round (BR-120)."""
        return MatchKey(round_no=self.round_count, is_third_place=False, position=1)


def bracket_of(
    first_round: Iterable[FirstRoundMatch], *, third_place_match: bool
) -> Bracket:
    """Check a stored first round and return its bracket (BR-040, BR-041).

    Raises:
        ValueError: The positions are not 1 to n for a power of two n, an
            entry is in two spots, a match has two byes, there are fewer than
            2 entries, or a third-place match with fewer than 4.
    """
    matches = tuple(sorted(first_round, key=lambda match: match.position))
    size = 2 * len(matches)
    if [match.position for match in matches] != list(range(1, len(matches) + 1)):
        msg = "the first round's positions are not 1 to n"
        raise ValueError(msg)
    seed_slots(size)  # raises unless a power of two
    entries = [
        side
        for match in matches
        for side in (match.side_1, match.side_2)
        if side is not None
    ]
    ensure_distinct(entries)
    if any(match.side_1 is None and match.side_2 is None for match in matches):
        msg = "a first-round match has two byes"
        raise ValueError(msg)
    if len(entries) < minimum_qualifiers(third_place_match=third_place_match):
        msg = f"{len(entries)} entries are too few for this knockout"
        raise ValueError(msg)
    return Bracket(size=size, third_place_match=third_place_match, first_round=matches)


def draw_bracket(seeds: Sequence[EntryId], *, third_place_match: bool) -> Bracket:
    """Place the seeds in a bracket (BR-040 to BR-042, BR-044).

    The bracket is the smallest power of two that fits (BR-040). Seed s meets
    the seed in the slot next to it (`seed_slots`); the slots of seeds beyond
    the entries are byes, so the byes go to the top seeds, one each, and only
    in the first round (BR-041): seed s has a bye exactly when `size + 1 - s`
    is not an entry. The better seed is side 1, a bye side 2.

    Args:
        seeds: The entries, seed 1 first.
        third_place_match: The semifinal losers play for 3rd (BR-044).

    Raises:
        ValueError: A caller bug: an entry is given twice, or there are fewer
            than 2 entries, 4 with a third-place match (BR-080).
    """
    seeds = tuple(seeds)
    ensure_distinct(seeds)
    size = bracket_size(len(seeds))
    slots = seed_slots(size)

    def at(slot: int) -> EntryId | None:
        return seeds[slot - 1] if slot <= len(seeds) else None

    return bracket_of(
        (
            FirstRoundMatch(
                position=index + 1,
                side_1=at(slots[2 * index]),
                side_2=at(slots[2 * index + 1]),
            )
            for index in range(size // 2)
        ),
        third_place_match=third_place_match,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class BracketMatch:
    """A match of the bracket with its sides as they stand (D4).

    Attributes:
        key: Where the match sits.
        side_1: Side 1: an entry, a bye, or not known yet.
        side_2: Side 2, the same.
        outcome: The stored result, None without one; a bye has none.
        winner: The entry that went through: the result's winner, or the
            entry against a bye (BR-041). None while undecided.
        loser: The entry that lost the result; None for a bye.
    """

    key: MatchKey
    side_1: Side
    side_2: Side
    outcome: Outcome | None
    winner: EntryId | None
    loser: EntryId | None

    @property
    def has_bye(self) -> bool:
        """A side is a bye, so the match is not played (BR-041)."""
        return self.side_1.is_bye or self.side_2.is_bye

    @property
    def is_playable(self) -> bool:
        """Both sides are entries: the match can take a field and a result (BR-091)."""
        return self.side_1.entry_id is not None and self.side_2.entry_id is not None


def _feeders(key: MatchKey) -> tuple[MatchKey, MatchKey]:
    """The two earlier matches whose winners, or semifinal losers, meet in `key`."""
    if key.is_third_place:
        return (
            MatchKey(round_no=key.round_no - 1, is_third_place=False, position=1),
            MatchKey(round_no=key.round_no - 1, is_third_place=False, position=2),
        )
    return (
        MatchKey(
            round_no=key.round_no - 1,
            is_third_place=False,
            position=2 * key.position - 1,
        ),
        MatchKey(
            round_no=key.round_no - 1, is_third_place=False, position=2 * key.position
        ),
    )


def play_bracket(
    bracket: Bracket, outcomes: Mapping[MatchKey, Outcome]
) -> tuple[BracketMatch, ...]:
    """Derive every match's sides from the first round and the results (D4, BR-094).

    A later standard match takes the winners of the two matches above it,
    side 1 from the upper one; the third-place match takes the semifinal
    losers, side 1 from the first semifinal (BR-044). The entry against a
    bye goes through without a result (BR-041). Changing a winner therefore
    changes the sides of the later matches on the next read.

    Args:
        bracket: The bracket.
        outcomes: The stored results by match. There are no draws (BR-043).

    Returns:
        Every match in schedule order (`Bracket.keys`).

    Raises:
        ValueError: A caller bug: a result for a match that is not in the
            bracket, for a bye, for a match whose sides are not both known,
            or a draw.
    """
    keys = bracket.keys
    unknown = set(outcomes) - set(keys)
    if unknown:
        msg = f"results for matches outside the bracket: {sorted(unknown)}"
        raise ValueError(msg)
    first = {match.position: match for match in bracket.first_round}
    played: dict[MatchKey, BracketMatch] = {}
    for key in keys:
        if key.round_no == 1:
            stored = first[key.position]
            sides = (
                _BYE if stored.side_1 is None else Side(entry_id=stored.side_1),
                _BYE if stored.side_2 is None else Side(entry_id=stored.side_2),
            )
        else:
            upper, lower = (played[feeder] for feeder in _feeders(key))
            sides = (
                (Side(entry_id=upper.loser), Side(entry_id=lower.loser))
                if key.is_third_place
                else (Side(entry_id=upper.winner), Side(entry_id=lower.winner))
            )
        played[key] = _decide(key, *sides, outcomes.get(key))
    return tuple(played[key] for key in keys)


def _decide(
    key: MatchKey, side_1: Side, side_2: Side, outcome: Outcome | None
) -> BracketMatch:
    winner = loser = None
    if side_1.is_bye or side_2.is_bye:
        if outcome is not None:
            msg = f"match {key} has a bye and a result"
            raise ValueError(msg)
        winner = side_2.entry_id if side_1.is_bye else side_1.entry_id
    elif outcome is not None:
        if side_1.entry_id is None or side_2.entry_id is None:
            msg = f"match {key} has a result but its sides are not known"
            raise ValueError(msg)
        if outcome is Outcome.DRAW:
            msg = f"match {key} is a draw, which a knockout has not (BR-043)"
            raise ValueError(msg)
        winner, loser = (
            (side_1.entry_id, side_2.entry_id)
            if outcome is Outcome.SIDE_1
            else (side_2.entry_id, side_1.entry_id)
        )
    return BracketMatch(
        key=key,
        side_1=side_1 if side_1.is_known else _UNKNOWN,
        side_2=side_2 if side_2.is_known else _UNKNOWN,
        outcome=outcome,
        winner=winner,
        loser=loser,
    )


def feeds(bracket: Bracket, key: MatchKey) -> tuple[MatchKey, ...]:
    """The later matches a match feeds (BR-094).

    Its winner's next match and, for a semifinal with a third-place match,
    that match for its loser.

    Raises:
        ValueError: `key` is not a match of the bracket.
    """
    if key not in bracket.keys:
        msg = f"match {key} is not in the bracket"
        raise ValueError(msg)
    if key.is_third_place or key.round_no == bracket.round_count:
        return ()
    later = [
        MatchKey(
            round_no=key.round_no + 1,
            is_third_place=False,
            position=(key.position + 1) // 2,
        )
    ]
    if bracket.third_place_match and key.round_no == bracket.round_count - 1:
        later.append(
            MatchKey(round_no=bracket.round_count, is_third_place=True, position=1)
        )
    return tuple(later)


def locked_by(
    bracket: Bracket, key: MatchKey, outcomes: Mapping[MatchKey, Outcome]
) -> tuple[MatchKey, ...]:
    """The later matches with a result that lock this match's result (BR-094).

    A result cannot be entered, changed or cleared while any match it feeds
    has a result; that result must be cleared first. Empty when the match is
    free to change.

    Raises:
        ValueError: `key` is not a match of the bracket.
    """
    return tuple(later for later in feeds(bracket, key) if later in outcomes)


def is_complete(matches: Iterable[BracketMatch]) -> bool:
    """Every match has a result, byes aside: the knockout is over (FR-037).

    The third-place match counts like any other, so a knockout with one is
    over only once it has a result too.
    """
    return all(match.outcome is not None for match in matches if not match.has_bye)


def knockout_results(matches: Iterable[BracketMatch]) -> tuple[KnockoutResult, ...]:
    """The results as `places.place_entries` reads them (BR-102).

    Byes are not matches and give no result (BR-041).
    """
    return tuple(
        KnockoutResult(
            round_no=match.key.round_no,
            winner_id=match.winner,
            loser_id=match.loser,
            is_third_place=match.key.is_third_place,
        )
        for match in matches
        if match.winner is not None and match.loser is not None
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Cut:
    """Who goes through to the knockout, and their seeds (BR-080, BR-085).

    Attributes:
        seeds: The qualifying entries, seed 1 first.
        decided_by_lot: The qualifiers that share their group-phase place
            with another entry, so the lot decided their seed, or whether
            they went through at all (BR-074, ADR-009).
        skipped: Disabled entries placed above the last qualifier, whom the
            next entries replaced (BR-080).
        is_cut_by_lot: The last qualifier shares their place with the first
            entry that does not go through, so the lot decided the cut.
    """

    seeds: tuple[EntryId, ...]
    decided_by_lot: frozenset[EntryId]
    skipped: tuple[EntryId, ...]
    is_cut_by_lot: bool


def cut_standing(
    standing: Iterable[Iterable[EntryId]],
    *,
    qualifiers: int,
    third_place_match: bool,
    rng_seed: bytes,
    disabled: Iterable[EntryId] = (),
) -> Cut:
    """Take the best entries of a group phase into the knockout (BR-080, BR-085).

    Entries play on as they are, seeded by their place (BR-085). Entries
    level in a tie group are put in a strict order by the lot
    `knockout-seeding` (BR-074, ADR-010), which decides both their seeds and,
    where the cut falls inside the group, who goes through. Disabled entries
    do not qualify and the next ones move up (BR-080).

    Args:
        standing: The group phase's tie groups, best first.
        qualifiers: How many entries go through (FR-045).
        third_place_match: The knockout has a third-place match (BR-044).
        rng_seed: The tournament's seed (ADR-010).
        disabled: The entries disabled now (FR-044).

    Raises:
        QualifierCountError: Fewer than 2 qualifiers, 4 with a third-place
            match, or more than the entries that are not disabled (BR-080).
        ValueError: A caller bug: an entry is given twice, or a disabled
            entry is not in the standing.
    """
    groups = [tuple(group) for group in standing]
    ensure_distinct(entry_id for group in groups for entry_id in group)
    off = set(disabled)
    if not off <= {entry_id for group in groups for entry_id in group}:
        msg = "a disabled entry is not in the standing"
        raise ValueError(msg)
    ordered = [
        (entry_id, index, len(group) > 1)
        for index, group in enumerate(groups)
        for entry_id in order_by_lot(
            group, rng_seed=rng_seed, purpose=KNOCKOUT_SEEDING_PURPOSE
        )
    ]
    eligible = [row for row in ordered if row[0] not in off]
    minimum = minimum_qualifiers(third_place_match=third_place_match)
    if not minimum <= qualifiers <= len(eligible):
        raise QualifierCountError(
            minimum=minimum, maximum=len(eligible), given=qualifiers
        )
    chosen = eligible[:qualifiers]
    last = ordered.index(chosen[-1])
    return Cut(
        seeds=tuple(entry_id for entry_id, _, _ in chosen),
        decided_by_lot=frozenset(entry_id for entry_id, _, tied in chosen if tied),
        skipped=tuple(entry_id for entry_id, _, _ in ordered[:last] if entry_id in off),
        is_cut_by_lot=len(eligible) > qualifiers
        and eligible[qualifiers][1] == chosen[-1][1],
    )
