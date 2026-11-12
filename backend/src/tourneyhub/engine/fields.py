"""Fields: the waiting list, the matches that take free fields, and placing by hand.

Field placements are stored; the application writes what `fill_fields` and
`place_by_hand` return in the same transaction as the event that frees a field
or makes a match playable. The waiting list is computed on every read
(DATA-MODEL D10). BR-130 to BR-134.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from tourneyhub.engine.errors import PlayerOnAnotherFieldError
from tourneyhub.engine.ids import FieldId, MatchId, PlayerId, ensure_distinct
from tourneyhub.engine.leagues import MAX_FIELD_COUNT
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
    """A waiting match that takes a free field, or a field let go (BR-130).

    Attributes:
        field_id: The field.
        match_id: The match that takes it, or None when the field lets go of
            a match that can no longer be played there and nothing takes its
            place.
    """

    field_id: FieldId
    match_id: MatchId | None


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

    A match can be on a field only while both its sides are known (BR-130).
    In a knockout a later match's sides come from earlier results (D4), so
    clearing or changing one can leave a match on a field with a side no
    longer known: its field lets go of it first, and the match waits again
    once its sides are known. Every other match already on a field stays
    there (BR-133), so a placement by hand holds.

    Then each free field, lowest number first, takes the first match of the
    waiting order none of whose players is on a field. A free field stays
    free when no waiting match can be played on it.

    Returns:
        The changed fields, lowest number first: a new match, or None for a
        field that let go of its match and took no other.

    Raises:
        ValueError: As for `waiting_order`.
    """
    matches = tuple(matches)
    fields = tuple(fields)
    _check(matches, fields)
    players = {match.match_id: match.player_ids for match in matches}
    let_go = {
        field.field_id
        for field in fields
        if field.match_id is not None and players[field.match_id] is None
    }
    fields = tuple(
        replace(field, match_id=None) if field.field_id in let_go else field
        for field in fields
    )
    waiting = list(waiting_order(matches=matches, fields=fields))
    busy = {
        player
        for field in fields
        if field.match_id is not None
        for player in players[field.match_id] or ()
    }
    placements: list[Placement] = []
    for field in sorted(fields, key=lambda field: field.number):
        if field.match_id is not None:
            continue
        match = next(
            (m for m in waiting if busy.isdisjoint(players[m.match_id] or ())), None
        )
        if match is None:
            if field.field_id in let_go:
                placements.append(Placement(field_id=field.field_id, match_id=None))
            continue
        waiting.remove(match)
        busy |= players[match.match_id] or frozenset()
        placements.append(Placement(field_id=field.field_id, match_id=match.match_id))
    return tuple(placements)


def next_field_number(numbers: Iterable[int]) -> int | None:
    """Return the number a new field gets: the lowest one no field has (BR-132).

    Returns:
        The lowest free number, or None when every number up to
        `MAX_FIELD_COUNT` is taken.
    """
    taken = set(numbers)
    return next((n for n in range(1, MAX_FIELD_COUNT + 1) if n not in taken), None)


@dataclass(frozen=True, slots=True, kw_only=True)
class HandPlacement:
    """Where the organizer puts a match by hand (FR-093, BR-133).

    Attributes:
        match_id: The match.
        field_id: The field it is played on, or None to send it back to
            waiting.
    """

    match_id: MatchId
    field_id: FieldId | None


def _check_hand_placements(
    matches: Sequence[MatchSlot],
    fields: Sequence[FieldSlot],
    placements: Sequence[HandPlacement],
) -> None:
    ensure_distinct(placement.match_id for placement in placements)
    ensure_distinct(p.field_id for p in placements if p.field_id is not None)
    by_id = {match.match_id: match for match in matches}
    field_ids = {field.field_id for field in fields}
    for placement in placements:
        match = by_id.get(placement.match_id)
        if match is None:
            msg = f"unknown match {placement.match_id}"
            raise ValueError(msg)
        if match.has_result or match.has_bye or match.player_ids is None:
            msg = f"match {match.match_id} cannot be played"
            raise ValueError(msg)
        if placement.field_id is not None and placement.field_id not in field_ids:
            msg = f"unknown field {placement.field_id}"
            raise ValueError(msg)


def _refuse_players_on_two_fields(
    matches: Sequence[MatchSlot], fields: Sequence[FieldSlot]
) -> None:
    """Raise when a player would be on two fields at once (BR-131)."""
    players = {match.match_id: match.player_ids or frozenset() for match in matches}
    fields_of: dict[PlayerId, list[FieldSlot]] = {}
    for field in sorted(fields, key=lambda field: field.number):
        if field.match_id is not None:
            for player in players[field.match_id]:
                fields_of.setdefault(player, []).append(field)
    twice = {player: on for player, on in fields_of.items() if len(on) > 1}
    if twice:
        involved = {field.field_id: field for on in twice.values() for field in on}
        raise PlayerOnAnotherFieldError(
            player_ids=tuple(sorted(twice)),
            field_ids=tuple(
                field.field_id
                for field in sorted(involved.values(), key=lambda f: f.number)
            ),
        )


def place_by_hand(
    *,
    matches: Iterable[MatchSlot],
    fields: Iterable[FieldSlot],
    placements: Iterable[HandPlacement],
) -> tuple[FieldSlot, ...]:
    """Put matches where the organizer says, then fill the free fields (FR-093).

    Every named match ends on its named field, or waiting when the field is
    None; the other fields keep their matches. A move names one match and
    its new field, a swap both matches with their new fields, so a repeat
    changes nothing. A field that loses its match and is not named is free.

    The free fields are then filled as by `fill_fields`, but not with a match
    this request sends back to waiting: it waits in schedule order and can
    take a field at the next fill. The filling never moves a match that is on
    a field, so a placement by hand holds until the match has a result
    (BR-133).

    Returns:
        Every field with its match afterwards, in the order of `fields`.

    Raises:
        PlayerOnAnotherFieldError: A player would be on two fields at once
            (BR-131); nothing is placed.
        ValueError: A match or a field is named twice or is unknown, a named
            match has a result, a bye or a side not known yet, or a named
            field keeps a match the request does not name: the caller checks
            these first. Also as for `waiting_order`.
    """
    matches = tuple(matches)
    fields = tuple(fields)
    placements = tuple(placements)
    _check(matches, fields)
    _check_hand_placements(matches, fields, placements)
    named = {placement.match_id for placement in placements}
    target = {p.field_id: p.match_id for p in placements if p.field_id is not None}
    placed: list[FieldSlot] = []
    for field in fields:
        kept = None if field.match_id in named else field.match_id
        if field.field_id in target:
            if kept is not None:
                msg = f"field {field.field_id} keeps match {kept}"
                raise ValueError(msg)
            kept = target[field.field_id]
        placed.append(replace(field, match_id=kept))
    _refuse_players_on_two_fields(matches, placed)
    sent_back = {p.match_id for p in placements if p.field_id is None}
    filled = {
        p.field_id: p.match_id
        for p in fill_fields(
            matches=[m for m in matches if m.match_id not in sent_back], fields=placed
        )
    }
    return tuple(
        replace(field, match_id=filled.get(field.field_id, field.match_id))
        for field in placed
    )
