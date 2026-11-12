"""Final places in a finished tournament (BR-100 to BR-104)."""

from collections.abc import Iterable
from dataclasses import dataclass

from tourneyhub.engine.ids import EntryId, PlayerId, ensure_distinct

type Standing = tuple[tuple[EntryId, ...], ...]
"""A group phase's standing: tie groups, best first (BR-074, BR-101).

Entries in one inner tuple are level and share the place.
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class PlacingEntry:
    """An entry to place: one player or one pair (BR-100).

    Attributes:
        entry_id: The entry.
        player_ids: The entry's one or two players. After a group phase they
            tell which group-phase entries went on to the knockout, since a
            knockout entry has an id of its own (DATA-MODEL §4.4).
        seed: The entry's setup seed, 1 for the best, or None without one.
            Entries sharing a place are listed by seed, seedless ones last.
    """

    entry_id: EntryId
    player_ids: tuple[PlayerId, ...]
    seed: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class KnockoutResult:
    """The result of one finished knockout match (BR-102).

    Attributes:
        round_no: 1 for the first round; the final has the highest number.
            Byes are not matches, so an entry that had one has no result
            in round 1.
        winner_id: The entry that won.
        loser_id: The entry that lost.
        is_third_place: The match is the third-place match, which has no
            round of its own.
    """

    round_no: int
    winner_id: EntryId
    loser_id: EntryId
    is_third_place: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class EntryPlace:
    """One entry's final place (BR-100, BR-104).

    Attributes:
        entry_id: The entry.
        player_ids: The entry's players, who all get its place (BR-100).
        place: 1 for the winner. Entries sharing a place have the same
            number, and the next place skips as many as they are (BR-104).
    """

    entry_id: EntryId
    player_ids: tuple[PlayerId, ...]
    place: int


def place_entries(
    entries: Iterable[PlacingEntry],
    *,
    standing: Iterable[Iterable[EntryId]] = (),
    knockout: Iterable[KnockoutResult] = (),
    third_place_match: bool = False,
) -> tuple[EntryPlace, ...]:
    """Place the entries of a finished tournament (BR-100 to BR-104).

    - **Group phase only:** pass `standing`. The places are the standing's
      places; entries level in a tie group share one (BR-101, BR-103).
    - **Knockout only:** pass `knockout`. The winner is 1st and the final's
      loser 2nd. With a third-place match its winner is 3rd and its loser
      4th; without one, the two semifinal losers share 3rd. Entries knocked
      out in the same earlier round share a place, which comes after every
      entry still in at that point (BR-102).
    - **Both:** the knockout entries take the top places and the rest follow
      in their `standing` order, numbered after the knockout entries
      (BR-103). A group-phase entry went on to the knockout when its players
      are all in knockout entries. An entry left without a place is refused.

    Places count entries, never players. A knockout pair is one entry, as is
    each non-qualifying player of a Monster DYP, so after 4 knockout pairs
    the best other player is 5th (PRD §5.2). This is a choice where BR-103
    does not say what Monster DYP counts: it follows the examples in PRD
    §5.1 and §5.2.

    `third_place_match` says whether the tournament has a third-place match.
    A knockout finishes only when every match has a result, the third-place
    match included (FR-037), so the results must hold an `is_third_place`
    result exactly when the flag is set. Tie groups that the knockout's cut
    splits stay together among the rest.

    The bracket's shape (byes only in round 1, BR-040 and BR-041) and the
    entry sizes are the bracket generator's job and are not validated here.

    Returns:
        One `EntryPlace` per placed entry, best place first and by seed
        within a place (seedless entries last, then by entry id). A group-phase entry that went on to the knockout is
        not listed; its knockout entry is.

    Raises:
        ValueError: A caller bug: an entry is given twice or is unknown, an
            entry would be placed twice or none, nothing was given to place,
            or the knockout has no single final, a third-place match that
            the flag does not match, a second third-place match, an entry
            that loses twice, or a third-place match that is not between the
            semifinal losers.
    """
    entries = tuple(entries)
    ensure_distinct(entry.entry_id for entry in entries)
    by_id = {entry.entry_id: entry for entry in entries}

    groups = tuple(tuple(group) for group in standing)
    results = tuple(knockout)
    has_third_place_result = any(result.is_third_place for result in results)
    if third_place_match and not has_third_place_result:
        msg = "the third-place match has no result"
        raise ValueError(msg)
    if has_third_place_result and not third_place_match:
        msg = "a third-place result was given for a knockout without that match"
        raise ValueError(msg)
    blocks = _knockout_blocks(results)
    knockout_players = {
        player_id
        for block in blocks
        for entry_id in block
        for player_id in _entry(by_id, entry_id).player_ids
    }
    for group in groups:
        remaining = tuple(
            entry_id
            for entry_id in group
            if knockout_players.isdisjoint(_entry(by_id, entry_id).player_ids)
        )
        if remaining:
            blocks.append(remaining)
    ensure_distinct(entry_id for block in blocks for entry_id in block)
    if not blocks:
        msg = "there is nothing to place"
        raise ValueError(msg)
    in_blocks = {entry_id for block in blocks for entry_id in block}
    for entry in entries:
        if entry.entry_id not in in_blocks and not knockout_players.issuperset(
            entry.player_ids
        ):
            msg = f"entry {entry.entry_id} is left without a place"
            raise ValueError(msg)

    placed: list[EntryPlace] = []
    place = 1
    for block in blocks:
        placed.extend(
            EntryPlace(
                entry_id=entry_id,
                player_ids=by_id[entry_id].player_ids,
                place=place,
            )
            for entry_id in sorted(block, key=lambda entry_id: _order(by_id[entry_id]))
        )
        place += len(block)
    return tuple(placed)


def _order(entry: PlacingEntry) -> tuple[bool, int, int]:
    """Order entries sharing a place: by seed, seedless last, then by id."""
    seed = entry.seed
    return (seed is None, 0 if seed is None else seed, entry.entry_id.int)


def _entry(by_id: dict[EntryId, PlacingEntry], entry_id: EntryId) -> PlacingEntry:
    try:
        return by_id[entry_id]
    except KeyError:
        msg = f"entry {entry_id} is not among the entries"
        raise ValueError(msg) from None


def _knockout_blocks(results: tuple[KnockoutResult, ...]) -> list[tuple[EntryId, ...]]:
    """Group the knockout's entries into blocks sharing a place, best first (BR-102)."""
    if not results:
        return []
    third_place = [result for result in results if result.is_third_place]
    bracket = [result for result in results if not result.is_third_place]
    if not bracket:
        msg = "a knockout needs a final"
        raise ValueError(msg)
    last_round = max(result.round_no for result in bracket)
    finals = [result for result in bracket if result.round_no == last_round]
    if len(finals) != 1:
        msg = f"round {last_round} has {len(finals)} matches, not one final"
        raise ValueError(msg)
    if len(third_place) > 1:
        msg = f"{len(third_place)} third-place matches"
        raise ValueError(msg)
    ensure_distinct(result.loser_id for result in bracket)

    final = finals[0]
    blocks: list[tuple[EntryId, ...]] = [(final.winner_id,), (final.loser_id,)]
    losers_by_round: dict[int, list[EntryId]] = {}
    for result in bracket:
        if result is not final:
            losers_by_round.setdefault(result.round_no, []).append(result.loser_id)

    semifinal_losers = losers_by_round.get(last_round - 1, [])
    if third_place:
        match = third_place[0]
        if {match.winner_id, match.loser_id} != set(semifinal_losers):
            msg = "the third-place match is not between the semifinal losers"
            raise ValueError(msg)
        blocks.extend([(match.winner_id,), (match.loser_id,)])
        del losers_by_round[last_round - 1]
    blocks.extend(
        tuple(losers_by_round[round_no])
        for round_no in sorted(losers_by_round, reverse=True)
    )
    return blocks
