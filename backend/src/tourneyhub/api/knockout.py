"""The knockout after a group phase: preview, start, final format, delete, bracket.

FR-045, FR-046, FR-054, BR-040 to BR-044, BR-080, BR-085 to BR-087, BR-094, BR-120.
Results go through `PUT …/matches/{match_id}/result` (`api.tournaments`).
The share link's bracket has an allowlisted model of its own (FR-070).
"""

from http import HTTPStatus
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import Field, JsonValue

from tourneyhub.api.deps import ClockDep, CurrentUserDep, SessionDep
from tourneyhub.api.public_headers import PUBLIC_PREFIX
from tourneyhub.api.schemas import INT_MAX, ErrorResponse, RequestModel, ResponseModel
from tourneyhub.api.tournament_models import TournamentRead
from tourneyhub.engine.knockout import MAX_KNOCKOUT_ENTRIES, RoundName
from tourneyhub.engine.tournaments import (
    KnockoutMatchFormat,
    MatchFormat,
    MatchKind,
    MonsterKnockoutMode,
    Outcome,
)
from tourneyhub.errors import ErrorCode
from tourneyhub.services import knockout as knockout_service
from tourneyhub.services.knockout import KnockoutStart

router = APIRouter(
    prefix="/leagues/{league_id}/tournaments/{tournament_id}",
    tags=["knockout"],
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND: {"model": ErrorResponse},
    },
)

public_router = APIRouter(
    prefix=PUBLIC_PREFIX + "/{share_token}/tournaments/{tournament_id}",
    tags=["public"],
    responses={HTTPStatus.NOT_FOUND: {"model": ErrorResponse}},
)

_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    HTTPStatus.CONFLICT: {"model": ErrorResponse},
    HTTPStatus.UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}

type Qualifiers = Annotated[int, Field(ge=2, le=MAX_KNOCKOUT_ENTRIES)]


class KnockoutProblemRead(ResponseModel):
    """Why starting the knockout would be refused: the error's code and detail."""

    code: ErrorCode
    detail: dict[str, JsonValue]


class KnockoutPreviewMemberRead(ResponseModel):
    """A group-phase entry behind a knockout entry, with its group-phase place."""

    entry_id: UUID
    place: int


class KnockoutPreviewEntryRead(ResponseModel):
    """A knockout entry by seed; `decided_by_lot` marks a lot's work (BR-074)."""

    seed: int
    members: list[KnockoutPreviewMemberRead]
    decided_by_lot: bool


class KnockoutPreviewRead(ResponseModel):
    """What starting the knockout would draw, writing nothing (FR-045, BR-080).

    `can_start` is false exactly when `problem` is set: the code and detail
    of the error `PUT …/knockout` would answer. `qualifiers` is the number
    asked for, kept between the fewest a knockout takes (2, or 4 with a
    third-place match) and `max_qualifiers`, the entries that can go through;
    when fewer than the fewest can, `entries` is empty. `first_round` pairs
    the seeds of each first-round match, null for a bye (BR-041), top of the
    bracket first. `locks_round_no` is the last group round, whose results
    the draw locks (BR-053). `is_cut_by_lot` says the cut fell inside a
    shared place, so the lot chose who goes through (BR-074). `draw_counter` is
    the tournament's; the start names it as `expected_draw_counter` (ADR-008).
    """

    can_start: bool
    problem: KnockoutProblemRead | None
    draw_counter: int
    max_qualifiers: int
    qualifiers: int
    entries: list[KnockoutPreviewEntryRead]
    first_round: list[tuple[int, int | None]]
    bracket_size: int | None
    locks_round_no: int | None
    skipped_entry_ids: list[UUID]
    is_cut_by_lot: bool


class KnockoutWrite(RequestModel):
    """Draw the knockout and start it (FR-045, BR-080, BR-120).

    `expected_current_phase_id` is the phase the screen saw as current, the
    group phase (ADR-008). `expected_draw_counter` is the preview's
    `draw_counter`: a stale one is 409 `draw_counter_changed`.
    `expected_qualifier_ids` are the group-phase entries the preview showed
    going through, in seed order (`entries` of the preview, by their members'
    `entry_id`). After Monster DYP rounds it lists every member of each pair,
    in seed order, and `qualifiers` counts players. A group result that changed
    the cut or the seeds since is 409 `qualifiers_changed`. `match_format` null takes
    the league's default; `final_match_format` null lets the final play
    `match_format` (BR-120).
    BO2 is never a knockout's (BR-121). `mode` is how the teams are formed
    after Monster DYP rounds (BR-081 to BR-084) and null after any other
    group phase; a mode after a round robin or a Swiss is 422
    `knockout_mode_not_applicable`.
    """

    expected_current_phase_id: UUID
    expected_draw_counter: Annotated[int, Field(ge=0, le=INT_MAX)]
    expected_qualifier_ids: Annotated[
        list[UUID], Field(max_length=2 * MAX_KNOCKOUT_ENTRIES)
    ]
    qualifiers: Qualifiers
    third_place_match: bool
    match_format: KnockoutMatchFormat | None
    final_match_format: KnockoutMatchFormat | None
    mode: MonsterKnockoutMode | None


class KnockoutDrawWrite(RequestModel):
    """Draw the knockout's pairs again (FR-045, ADR-010).

    `expected_draw_counter` is the preview's `draw_counter`.
    """

    expected_draw_counter: Annotated[int, Field(ge=0, le=INT_MAX)]


class KnockoutDrawRead(ResponseModel):
    """The draw counter after drawing again; preview again to see the new pairs."""

    draw_counter: int


class FinalFormatWrite(RequestModel):
    """The final's own format, or null to play the knockout's (FR-054, BR-120).

    BO2 is never a knockout's (BR-121).
    """

    final_match_format: KnockoutMatchFormat | None


type MatchState = Literal["bye", "played", "on_field", "ready", "waiting"]


class BracketSideRead(ResponseModel):
    """A side: the entry and its knockout seed, a bye, or null while to come.

    `decided_by_lot` says a lot placed the entry among those level with it in
    the group phase, or took it through the cut (BR-074, ADR-009).
    """

    entry_id: UUID | None
    seed: int | None
    is_bye: bool
    decided_by_lot: bool


class BracketMatchRead(ResponseModel):
    """A bracket match with its sides derived from the results (D4).

    `number` counts the tournament's matches, the group phase's first; a bye
    has none (BR-041). `state`: `bye`; `played`; `on_field`; `ready` (both
    sides known, no field); `waiting` (a side still to come). `score` is
    side 1's: a BO1 game's goals, else the games won; null before a result
    or for a walkover. `next_number` is the match the winner plays next.
    `result_locked` says a later match it feeds has a result, so this one
    cannot change until that is cleared (BR-094).
    """

    match_id: UUID
    number: int | None
    round_no: int
    position: int
    kind: MatchKind
    state: MatchState
    sides: tuple[BracketSideRead, BracketSideRead]
    outcome: Outcome | None
    is_walkover: bool
    score: tuple[int, int] | None
    match_format: MatchFormat
    field_number: int | None
    next_number: int | None
    result_locked: bool


class BracketRoundRead(ResponseModel):
    """A round of the bracket; the last holds the final and the third-place match."""

    round_no: int
    name: RoundName
    matches: list[BracketMatchRead]


class BracketRead(ResponseModel):
    """The knockout, computed on read (D4, screens 9 and 10).

    `size` is the smallest power of two that fits the entries (BR-040). The
    final plays `final_match_format`, or `match_format` when it is null
    (BR-120).
    """

    phase_id: UUID
    size: int
    third_place_match: bool
    has_group_phase: bool
    match_format: MatchFormat
    final_match_format: KnockoutMatchFormat | None
    rounds: list[BracketRoundRead]


class PublicBracketSideRead(ResponseModel):
    """A side for viewers: the entry, its seed and whether a lot decided it, or a bye."""

    entry_id: UUID | None
    seed: int | None
    is_bye: bool
    decided_by_lot: bool


class PublicBracketMatchRead(ResponseModel):
    """A bracket match for viewers (FR-072); `result_locked` is the organizer's."""

    match_id: UUID
    number: int | None
    round_no: int
    position: int
    kind: MatchKind
    state: MatchState
    sides: tuple[PublicBracketSideRead, PublicBracketSideRead]
    outcome: Outcome | None
    is_walkover: bool
    score: tuple[int, int] | None
    match_format: MatchFormat
    field_number: int | None
    next_number: int | None


class PublicBracketRoundRead(ResponseModel):
    round_no: int
    name: RoundName
    matches: list[PublicBracketMatchRead]


class PublicBracketRead(ResponseModel):
    """The knockout through the share link (FR-070).

    A separate allowlist of fields, not a copy of the organizer's bracket: a
    field added there must not reach viewers until it is added here on
    purpose. Today it holds the same fields, all of which the share link's
    tournament already shows or derives from what it shows.
    """

    phase_id: UUID
    size: int
    third_place_match: bool
    has_group_phase: bool
    match_format: MatchFormat
    final_match_format: KnockoutMatchFormat | None
    rounds: list[PublicBracketRoundRead]


@router.get("/knockout/preview")
def read_knockout_preview(
    league_id: UUID,
    tournament_id: UUID,
    qualifiers: Annotated[int, Query(ge=2, le=MAX_KNOCKOUT_ENTRIES)],
    third_place_match: bool,  # noqa: FBT001  (a query parameter, not a flag argument)
    session: SessionDep,
    user: CurrentUserDep,
    mode: MonsterKnockoutMode | None = None,
) -> KnockoutPreviewRead:
    """Return the cut, the seeds and the byes the knockout would get (FR-045).

    Writes nothing. A knockout that cannot start is still 200, with the
    `problem` its start would answer: `tournament_not_in_progress`,
    `current_phase_changed` (the knockout exists), `season_closed`,
    `format_not_supported` (no group phase),
    `knockout_mode_required` (Monster DYP rounds without a `mode`),
    `group_phase_not_done` or `knockout_mode_not_applicable` (a `mode` after a
    round robin or a Swiss). After Monster DYP rounds `qualifiers` counts
    players and a pair mode shows an even count of at least twice the fewest
    entries (BR-080).
    """
    preview = knockout_service.preview_knockout(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        qualifiers=qualifiers,
        third_place_match=third_place_match,
        mode=mode,
    )
    return KnockoutPreviewRead.model_validate(
        {
            "can_start": preview.problem is None,
            "problem": preview.problem,
            "draw_counter": preview.draw_counter,
            "max_qualifiers": preview.max_qualifiers,
            "qualifiers": preview.qualifiers,
            "entries": preview.entries,
            "first_round": preview.first_round,
            "bracket_size": preview.bracket_size,
            "locks_round_no": preview.locks_round_no,
            "skipped_entry_ids": preview.skipped_entry_ids,
            "is_cut_by_lot": preview.is_cut_by_lot,
        }
    )


@router.put("/knockout", responses=_WRITE_ERRORS)
def start_knockout(
    league_id: UUID,
    tournament_id: UUID,
    body: KnockoutWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentRead:
    """Draw the knockout after the round robin or the Swiss and start it (FR-045).

    The best entries of the standings go through as they are, seeded by their
    place; entries still level are ordered by lot (BR-074, BR-080, BR-085).
    The byes go to the top seeds (BR-040 to BR-042); the first matches take
    the free fields, and the group phase's results lock (BR-053, BR-065).
    A Lord have mercy knockout (BR-084) stores only round 1; the later rounds
    are drawn one at a time.

    409: `tournament_not_in_progress` (detail `state`), `current_phase_changed`
    (the knockout already exists, detail `current_phase_id`),
    `draw_counter_changed` (detail `draw_counter`, the current one),
    `qualifiers_changed` (the cut or the seeds are not the previewed ones,
    detail `entry_ids`, the current ones) or `season_closed`. 422:
    `format_not_supported` (no group phase; detail `format`),
    `knockout_mode_required` (Monster DYP rounds without a `mode`; detail
    `format`),
    `group_phase_not_done` (detail `matches_left`), `qualifiers_odd` (a pair
    mode with an odd number; detail `given`), `qualifiers_out_of_range`
    (detail `minimum`, `maximum`, `given`) or `knockout_mode_not_applicable`
    (detail `format`).
    """
    tournament = knockout_service.start_knockout(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        start=KnockoutStart(
            expected_current_phase_id=body.expected_current_phase_id,
            expected_draw_counter=body.expected_draw_counter,
            expected_qualifier_ids=tuple(body.expected_qualifier_ids),
            qualifiers=body.qualifiers,
            third_place_match=body.third_place_match,
            match_format=body.match_format,
            final_match_format=body.final_match_format,
            mode=body.mode,
        ),
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


@router.post("/knockout/draw", responses=_WRITE_ERRORS)
def draw_knockout_again(
    league_id: UUID,
    tournament_id: UUID,
    body: KnockoutDrawWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> KnockoutDrawRead:
    """Draw the knockout's pairs again after Monster DYP rounds (FR-045, BR-083).

    Counts the draw counter up; the next preview shows the new lots (ADR-010).
    Accepted in every Monster DYP mode. A stale `expected_draw_counter` is 409
    `draw_counter_changed` with the current `draw_counter`. 409 `season_closed`,
    `tournament_not_in_progress` (detail `state`) or `current_phase_changed`
    once the knockout exists; 422 `knockout_mode_not_applicable` when the group
    phase is not Monster DYP.
    """
    draw_counter = knockout_service.draw_knockout_again(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        expected_draw_counter=body.expected_draw_counter,
        clock=clock,
    )
    return KnockoutDrawRead(draw_counter=draw_counter)


@router.put("/knockout/final-format", responses=_WRITE_ERRORS)
def set_final_format(
    league_id: UUID,
    tournament_id: UUID,
    body: FinalFormatWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentRead:
    """Change the final's format while the final has no result (FR-054, BR-120).

    Null lets the final play the knockout's format again; the third-place
    match always plays it. 404 `knockout_not_found` without a knockout. 409
    `tournament_not_in_progress` in setup (detail `state`), `season_closed` or
    `match_has_result` once the final has a result (BR-096, detail
    `match_id`), so also in a finished tournament.
    """
    tournament = knockout_service.set_final_format(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        final_match_format=body.final_match_format,
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


@router.delete(
    "/phases/{phase_id}", status_code=HTTPStatus.NO_CONTENT, responses=_WRITE_ERRORS
)
def delete_knockout(
    league_id: UUID,
    tournament_id: UUID,
    phase_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> None:
    """Delete the knockout that follows the group phase, with its results (FR-046).

    The group phase unlocks, all of a round robin's results or the newest
    round of a Swiss or Monster DYP, and the organizer chooses again what
    comes next (BR-087, BR-065: a Swiss can then also add a round); a
    finished tournament is back in progress. The phase is named by its id: a repeat is 404 `phase_not_found` (ADR-008).
    409 `season_closed`. 422 `phase_not_deletable` for a group phase or a
    knockout without a group phase (detail `kind`).
    """
    knockout_service.delete_knockout(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        phase_id=phase_id,
        user_id=user.id,
        clock=clock,
    )


@router.get("/bracket")
def read_bracket(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> BracketRead:
    """Return the knockout with its sides derived from the results (D4).

    A tournament without a knockout is 404 `knockout_not_found`.
    """
    bracket = knockout_service.read_bracket(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return BracketRead.model_validate(bracket)


@public_router.get("/bracket")
def read_public_bracket(
    share_token: str, tournament_id: UUID, session: SessionDep
) -> PublicBracketRead:
    """Return a tournament's knockout through the share link (FR-070).

    A tournament without a knockout is 404 `knockout_not_found`; one in setup
    is 404 `tournament_not_found`, like an unknown one or one of another
    league.
    """
    bracket = knockout_service.read_shared_bracket(
        session, share_token=share_token, tournament_id=tournament_id
    )
    return PublicBracketRead.model_validate(bracket)
