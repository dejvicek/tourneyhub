"""Fields: filling them, adding and removing them, placing matches."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy.orm import Session

from tourneyhub.db.models.tournaments import Field, Tournament
from tourneyhub.engine.errors import EngineError
from tourneyhub.engine.fields import (
    FieldSlot,
    HandPlacement,
    MatchSlot,
    fill_fields,
    next_field_number,
    place_by_hand,
)
from tourneyhub.engine.ids import FieldId, MatchId
from tourneyhub.engine.tournaments import TournamentState
from tourneyhub.errors import (
    ConflictError,
    ErrorCode,
    NotFoundError,
    RuleViolationError,
)
from tourneyhub.services.engine_errors import to_app_error
from tourneyhub.services.tournaments.shared import (
    Clock,
    _field_slots,
    _find_match,
    _lock_tournament,
    _match_players,
    _match_slots,
)
from tourneyhub.services.tournaments.views import (
    FieldView,
    TournamentView,
    read_tournament,
)


def _fill_fields(
    tournament: Tournament, slots: Sequence[MatchSlot], now: datetime
) -> None:
    """Put waiting matches on the free fields (BR-130, BR-131, DATA-MODEL §4.6).

    A requeued match that takes a field is no longer requeued (BR-132).
    """
    placements = fill_fields(matches=slots, fields=_field_slots(tournament))
    fields = {field.id: field for field in tournament.fields}
    requeued = {slot.match_id for slot in slots if slot.requeued_at is not None}
    for placement in placements:
        field = fields[placement.field_id]
        field.match_id = placement.match_id
        field.updated_at = now
        if placement.match_id in requeued:
            _find_match(tournament, placement.match_id)[2].requeued_at = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FieldPlacement:
    """A match placed by hand: on a field, or back to waiting with no field (FR-093).

    `from_field_id` is the field the screen saw the match on, None for waiting.
    """

    match_id: UUID
    field_id: UUID | None
    from_field_id: UUID | None


def _lock_running(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> Tournament:
    """Lock a tournament in progress, with its rounds, for a change to its fields.

    Fields are added, removed and given matches while the tournament runs
    (FR-090); in setup or once finished it is 409 `tournament_not_in_progress`.
    """
    _, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    if tournament.state is not TournamentState.IN_PROGRESS:
        raise ConflictError(
            ErrorCode.TOURNAMENT_NOT_IN_PROGRESS, state=tournament.state
        )
    return tournament


def add_field(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    number: int,
    clock: Clock,
) -> FieldView:
    """Add a field; it takes the next waiting match at once (FR-090, BR-132).

    The request carries the number it expects the field to get, the lowest
    free one (ADR-008). Any other number, a repeat included, is 409
    `field_number_changed` with the `number` a new field would get now, null
    once every number up to 32 is taken.
    """
    tournament = _lock_running(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    expected = next_field_number(field.number for field in tournament.fields)
    if number != expected:
        raise ConflictError(ErrorCode.FIELD_NUMBER_CHANGED, number=expected)
    now = clock()
    field = Field(id=uuid7(), number=number, created_at=now)
    tournament.fields.append(field)
    _fill_fields(tournament, _match_slots(tournament), now)
    session.flush()
    return FieldView(id=field.id, number=field.number, match_id=field.match_id)


def remove_field(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    field_id: UUID,
    user_id: UUID,
    clock: Clock,
) -> None:
    """Remove a field by its id; the others keep their numbers (FR-090, BR-132).

    The match on it goes to the front of the waiting list (`requeued_at`),
    and the free fields are filled, so it can take another free field at
    once. An unknown field, one of another tournament or a repeated delete is
    404 `field_not_found`; the last field is 422 `last_field`.
    """
    tournament = _lock_running(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    field = next((f for f in tournament.fields if f.id == field_id), None)
    if field is None:
        raise NotFoundError(ErrorCode.FIELD_NOT_FOUND)
    if len(tournament.fields) == 1:
        raise RuleViolationError(ErrorCode.LAST_FIELD)
    now = clock()
    if field.match_id is not None:
        _find_match(tournament, field.match_id)[2].requeued_at = now
    tournament.fields.remove(field)
    session.flush()  # the field lets go of its match before another field takes it
    _fill_fields(tournament, _match_slots(tournament), now)
    session.flush()


def _check_placements(
    tournament: Tournament, placements: Sequence[FieldPlacement]
) -> None:
    """Refuse placements the current state does not allow (ADR-008, FR-093).

    Unknown ids are 404. A match with a result, a match that is not where the
    screen saw it (`from_field_id`) or a field that holds a match the request
    does not name only reach here from a stale screen: 409. A side not known
    yet, or a bye, is 422 `match_sides_unknown` (BR-091). Of what is left,
    only the four operations of FR-093 are allowed (`_refuse_other_operations`).
    """
    fields = {field.id: field for field in tournament.fields}
    named = {placement.match_id for placement in placements}
    found = [
        (_find_match(tournament, placement.match_id)[2], placement)
        for placement in placements
    ]
    if any(p.field_id is not None and p.field_id not in fields for p in placements):
        raise NotFoundError(ErrorCode.FIELD_NOT_FOUND)
    players = _match_players(tournament)
    for match, _ in found:
        if match.outcome is not None:
            raise ConflictError(ErrorCode.MATCH_HAS_RESULT, match_id=str(match.id))
        if players[match.id] is None or any(side.is_bye for side in match.sides):
            raise RuleViolationError(ErrorCode.MATCH_SIDES_UNKNOWN)
    seen = {f.match_id: f.id for f in tournament.fields if f.match_id is not None}
    if any(seen.get(p.match_id) != p.from_field_id for p in placements):
        raise ConflictError(ErrorCode.PLACEMENT_CHANGED)
    for placement in placements:
        if placement.field_id is None:
            continue
        held = fields[placement.field_id].match_id
        if held is not None and held not in named:
            raise ConflictError(
                ErrorCode.FIELD_NOT_FREE,
                field_id=str(placement.field_id),
                match_id=str(held),
            )
    _refuse_other_operations(placements)


def _refuse_other_operations(placements: Sequence[FieldPlacement]) -> None:
    """Allow only the four operations of FR-093, else 422 `placement_not_allowed`.

    A waiting match on a free field, a match from its field to a free field,
    a match back to waiting, and a swap of two matches that are both on
    fields. Replacing the match on a field and a rotation are not allowed
    until the PRD decides whether they should exist. A free target field is
    checked before (`field_not_free`), so a single placement only has to
    change something.
    """
    if len(placements) == 1:
        (only,) = placements
        allowed = only.field_id != only.from_field_id
    else:
        first, second = placements
        allowed = (
            first.from_field_id is not None
            and second.from_field_id is not None
            and first.field_id == second.from_field_id
            and second.field_id == first.from_field_id
        )
    if not allowed:
        raise RuleViolationError(ErrorCode.PLACEMENT_NOT_ALLOWED)


def _store_fields(
    session: Session,
    tournament: Tournament,
    placed: Iterable[FieldSlot],
    now: datetime,
) -> None:
    """Write each field's match; a match that takes a field is no longer requeued."""
    rows = {field.id: field for field in tournament.fields}
    changed = [
        (rows[slot.field_id], slot.match_id)
        for slot in placed
        if rows[slot.field_id].match_id != slot.match_id
    ]
    if not changed:
        return
    for field, _ in changed:
        field.match_id = None
    # A match moving to another field leaves the old one first: `fields.match_id`
    # is unique, and a swap would hold one match on two fields in between.
    session.flush()
    for field, match_id in changed:
        field.match_id = match_id
        field.updated_at = now
        if match_id is not None:
            _find_match(tournament, match_id)[2].requeued_at = None


def place_matches(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    placements: Sequence[FieldPlacement],
    clock: Clock,
) -> TournamentView:
    """Place, move, swap or take off matches by hand, the target state (FR-093).

    Each named match ends on its named field, or waiting without one; a swap
    names both matches with their new fields (ADR-008). A field that a match leaves and that is not named takes the
    next waiting match, but not one this request sends back to waiting: that
    one waits in schedule order (DATA-MODEL §4.6). The filling never moves a
    match on a field, so a placement by hand holds until its result (BR-133).

    Refusals: `_check_placements`, then 422 `player_on_another_field` when a
    player would be on two fields at once (BR-131).
    """
    tournament = _lock_running(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _check_placements(tournament, placements)
    try:
        placed = place_by_hand(
            matches=_match_slots(tournament),
            fields=_field_slots(tournament),
            placements=[
                HandPlacement(
                    match_id=MatchId(p.match_id),
                    field_id=None if p.field_id is None else FieldId(p.field_id),
                )
                for p in placements
            ],
        )
    except EngineError as err:
        raise to_app_error(err) from err
    _store_fields(session, tournament, placed, clock())
    session.flush()
    return read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )
