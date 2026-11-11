"""Fields: the waiting list and the matches that take free fields (BR-130 to BR-132).

Field placements are stored; the application writes what `fill_fields`
returns in the same transaction as the event that frees a field or makes a
match playable. The waiting list is computed on every read (DATA-MODEL D10).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from tourneyhub.engine.ids import FieldId, MatchId, PlayerId, ensure_distinct
from tourneyhub.engine.tournaments import MatchKind


@dataclass(frozen=True, slots=True, kw_only=True)
class MatchSlot:
    """A match as the field queue sees it.

    Attributes:
        match_id: The match.
        phase_position: The position of the match's phase, 1 first (D9).
        round_no: The match's round within its phase.
        kind: Within a round, the standard matches come before the
            third-place match.
        position: The match's order within its round and kind.
        player_ids: Every player of both sides, or None while a side is not
            known yet (D4).
        has_bye: A side is a bye; such a match is never played (BR-041).
        has_result: The match has a result or a walkover (D11).
        requeued_at: When the field the match was on was removed (BR-132);
            None otherwise.
    """

    match_id: MatchId
    phase_position: int
    round_no: int
    kind: MatchKind
    position: int
    player_ids: frozenset[PlayerId] | None
    has_bye: bool
    has_result: bool
    requeued_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class FieldSlot:
    """A field and the match on it, if any (DATA-MODEL §4.6).

    Attributes:
        field_id: The field.
        number: The field's number, shown as "Field" and the number (FR-091).
        match_id: The match being played on it, or None while it is free.
    """

    field_id: FieldId
    number: int
    match_id: MatchId | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Placement:
    """A waiting match that takes a free field (BR-130).

    Attributes:
        field_id: The free field.
        match_id: The match that takes it.
    """

    field_id: FieldId
    match_id: MatchId


def _schedule_key(match: MatchSlot) -> tuple[int, int, bool, int]:
    return (
        match.phase_position,
        match.round_no,
        match.kind is MatchKind.THIRD_PLACE,
        match.position,
    )


def _check(matches: Iterable[MatchSlot], fields: Iterable[FieldSlot]) -> None:
    ensure_distinct(match.match_id for match in matches)
    ensure_distinct(field.field_id for field in fields)
    ensure_distinct(field.match_id for field in fields if field.match_id is not None)
    known = {match.match_id for match in matches}
    for field in fields:
        if field.match_id is not None and field.match_id not in known:
            msg = f"field {field.field_id} holds an unknown match {field.match_id}"
            raise ValueError(msg)


def waiting_order(
    *, matches: Iterable[MatchSlot], fields: Iterable[FieldSlot]
) -> tuple[MatchSlot, ...]:
    """Return the matches waiting for a field, in the order they get one (FR-092).

    A match waits while it has no result, is on no field, has no bye side
    and both its sides are known. Requeued matches come first, earliest
    first (BR-132); then the schedule order of BR-130: by phase, by round,
    then by match within the round, the third-place match after the others.

    Raises:
        ValueError: A match or a field is given twice, two fields hold one
            match, or a field holds a match that is not in `matches`.
    """
    matches = tuple(matches)
    fields = tuple(fields)
    _check(matches, fields)
    on_field = {field.match_id for field in fields}
    waiting = [
        match
        for match in matches
        if not match.has_result
        and not match.has_bye
        and match.player_ids is not None
        and match.match_id not in on_field
    ]
    requeued = sorted(
        (match for match in waiting if match.requeued_at is not None),
        key=lambda match: (match.requeued_at, _schedule_key(match)),
    )
    in_order = sorted(
        (match for match in waiting if match.requeued_at is None), key=_schedule_key
    )
    return (*requeued, *in_order)


def fill_fields(
    *, matches: Iterable[MatchSlot], fields: Iterable[FieldSlot]
) -> tuple[Placement, ...]:
    """Put waiting matches on the free fields (BR-130, BR-131).

    Each free field, lowest number first, takes the first match of the
    waiting order none of whose players is on a field. A match already on a
    field stays there (BR-133), so a placement by hand holds. A free field
    stays free when no waiting match can be played on it.

    Returns:
        The new placements, lowest field number first.

    Raises:
        ValueError: As for `waiting_order`.
    """
    matches = tuple(matches)
    fields = tuple(fields)
    waiting = list(waiting_order(matches=matches, fields=fields))
    players = {match.match_id: match.player_ids or frozenset() for match in matches}
    busy = {
        player
        for field in fields
        if field.match_id is not None
        for player in players[field.match_id]
    }
    placements: list[Placement] = []
    for field in sorted(fields, key=lambda field: field.number):
        if field.match_id is not None:
            continue
        match = next((m for m in waiting if busy.isdisjoint(players[m.match_id])), None)
        if match is None:
            continue
        waiting.remove(match)
        busy |= players[match.match_id]
        placements.append(Placement(field_id=field.field_id, match_id=match.match_id))
    return tuple(placements)
