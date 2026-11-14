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
from tourneyhub.api.tournament_models import RoundCreate, TournamentRead
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
from tourneyhub.services import remix as remix_service
from tourneyhub.services.knockout import KnockoutStart
from tourneyhub.services.remix import RemixMatchState, RemixPlayerStatus

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

_REFUSED: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}
"""A read of a knockout that is not of the shape asked for is 422 (BR-155)."""

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


class RemixReplacementRead(ResponseModel):
    """A player who came into a draw in place of a player who left (BR-148, BR-155).

    `player_id` came in; `replaced_player_id` left and was replaced.
    """

    player_id: UUID
    replaced_player_id: UUID


class RemixSideRead(ResponseModel):
    """A side of a Lord have mercy match: a pair of players, or a bye (BR-041).

    `entry_id` is the round-1 pair entry; a later round's pair has none (D4).
    `player_ids` is empty for a bye. `left_player_ids` are the pair's players
    who have left but stay in the draw (BR-147, BR-149). `replacements` are the
    pair's players who came in for a player who left, and for whom (BR-155);
    empty in round 1.
    """

    player_ids: list[UUID]
    entry_id: UUID | None
    is_bye: bool
    left_player_ids: list[UUID]
    replacements: list[RemixReplacementRead]


class RemixMatchRead(ResponseModel):
    """A match of a drawn Lord have mercy round (BR-155).

    `number` counts the tournament's matches, the group phase's first; a bye
    has none, and the third-place match comes after the final. `state`: `bye`;
    `played`; `on_field`; `ready`. `score` is side 1's: a BO1 game's goals,
    else the games won. `winner_locked` says a later round is drawn, so the
    result can be corrected but not cleared or given to the other pair
    (BR-146).
    """

    match_id: UUID
    number: int | None
    position: int
    kind: MatchKind
    state: RemixMatchState
    sides: tuple[RemixSideRead, RemixSideRead]
    outcome: Outcome | None
    is_walkover: bool
    score: tuple[int, int] | None
    match_format: MatchFormat
    field_number: int | None
    winner_locked: bool


class RemixRoundRead(ResponseModel):
    """A drawn round; `result_count` counts the matches with a result in it."""

    round_id: UUID
    round_no: int
    name: RoundName
    result_count: int
    matches: list[RemixMatchRead]


class RemixNextDrawRead(ResponseModel):
    """What drawing the next round would do now (FR-049, BR-148, BR-149).

    `replacements` would come in for players who left, the replaced player
    with the best group-phase standing first; `staying_player_ids` have left
    but would stay in the draw without one, since nobody is available, and
    their pair loses by walkover (BR-149). Disabling or re-enabling a player
    changes it; the draw makes exactly this plan.
    """

    replacements: list[RemixReplacementRead]
    staying_player_ids: list[UUID]


class RemixPlayerRead(ResponseModel):
    """A player of the knockout, for the disable switch (FR-044, BR-147).

    `entry_id` is the player's main entry, which `PUT …/entries/{entry_id}/
    disabled` takes. `status`: `still_in` (their latest pair won, had a bye or
    has no result yet, or waits for the third-place match), `knocked_out`, or
    `replaced` once a replacement came in for them (BR-153). `is_disabled` is
    the main entry's flag; a disabled player who is still in has left.
    """

    player_id: UUID
    entry_id: UUID
    status: RemixPlayerStatus
    is_disabled: bool


class RemixKnockoutRead(ResponseModel):
    """A Lord have mercy knockout round by round, computed on read (D4, BR-155).

    `size` is twice the round-1 matches and `round_count` the rounds the
    knockout will have; `rounds` holds those drawn so far. `can_draw_next` says
    the next round can be drawn (BR-140). `left_player_ids` are all the players
    who have left but stay in (FR-049). The final plays `final_match_format`,
    or `match_format` when it is null (BR-120). `next_draw` previews the next
    draw's replacements, null unless the tournament is in progress and the
    next round can be drawn (FR-049). `players` lists the knockout's players by
    group-phase standing.
    """

    phase_id: UUID
    size: int
    round_count: int
    third_place_match: bool
    match_format: MatchFormat
    final_match_format: KnockoutMatchFormat | None
    can_draw_next: bool
    left_player_ids: list[UUID]
    rounds: list[RemixRoundRead]
    next_draw: RemixNextDrawRead | None
    players: list[RemixPlayerRead]


class PublicRemixSideRead(ResponseModel):
    """A side of a Lord have mercy match for viewers (FR-070, FR-049, BR-155)."""

    player_ids: list[UUID]
    entry_id: UUID | None
    is_bye: bool
    left_player_ids: list[UUID]
    replacements: list[RemixReplacementRead]


class PublicRemixMatchRead(ResponseModel):
    """A match of a drawn Lord have mercy round for viewers; no `winner_locked`."""

    match_id: UUID
    number: int | None
    position: int
    kind: MatchKind
    state: RemixMatchState
    sides: tuple[PublicRemixSideRead, PublicRemixSideRead]
    outcome: Outcome | None
    is_walkover: bool
    score: tuple[int, int] | None
    match_format: MatchFormat
    field_number: int | None


class PublicRemixRoundRead(ResponseModel):
    round_id: UUID
    round_no: int
    name: RoundName
    matches: list[PublicRemixMatchRead]


class PublicRemixKnockoutRead(ResponseModel):
    """A Lord have mercy knockout round by round through the share link (FR-070).

    A separate allowlist, like `PublicBracketRead`: it leaves out what is the
    organizer's, `can_draw_next`, `result_count`, `winner_locked`, `next_draw`
    and `players` (BR-140, BR-146, FR-049), and keeps `left_player_ids` and the
    sides' `replacements` (BR-155).
    """

    phase_id: UUID
    size: int
    round_count: int
    third_place_match: bool
    match_format: MatchFormat
    final_match_format: KnockoutMatchFormat | None
    left_player_ids: list[UUID]
    rounds: list[PublicRemixRoundRead]


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


@router.post(
    "/knockout/rounds", status_code=HTTPStatus.CREATED, responses=_WRITE_ERRORS
)
def draw_knockout_round(
    league_id: UUID,
    tournament_id: UUID,
    body: RoundCreate,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> RemixKnockoutRead:
    """Draw the next round of a Lord have mercy knockout (BR-140 to BR-144, BR-156).

    The round before must be complete (BR-140). The players who went through
    are paired by lot; the final's round is drawn the same way (BR-141,
    BR-142) with the third-place match among the semifinal losers (BR-144).
    The lots hold no draw counter, so the same players always give the same
    pairs (BR-156, ADR-010). Disabled players still in are drawn like everyone
    else (BR-149). The new matches take the free fields, the third-place match
    after the final (BR-130), and the winners of the round before are locked
    (BR-146). Returns the knockout round by round.

    404 `knockout_not_found` without a knockout. 409: `round_number_changed`
    (`expected_round_no` is not the rounds drawn plus one; detail
    `current_round_no`, the newest round's), `tournament_not_in_progress`
    (detail `state`) or `season_closed`. 422: `format_not_supported` (a
    fixed-pair knockout; detail `format`, `mode`) or `round_not_complete` (a
    match of the newest round has no result; detail `matches_left`).
    """
    knockout = remix_service.draw_knockout_round(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        expected_round_no=body.expected_round_no,
        clock=clock,
    )
    return RemixKnockoutRead.model_validate(knockout)


@router.get("/knockout/rounds", responses=_REFUSED)
def read_knockout_rounds(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> RemixKnockoutRead:
    """Return a Lord have mercy knockout round by round (BR-155, FR-049).

    Computed on read from the rounds drawn so far. 404 `knockout_not_found`
    without a knockout; 422 `format_not_supported` (detail `format`, `mode`)
    for a fixed-pair knockout, which `…/bracket` serves.
    """
    knockout = remix_service.read_knockout_rounds(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return RemixKnockoutRead.model_validate(knockout)


@router.delete(
    "/knockout/rounds/{round_id}",
    status_code=HTTPStatus.NO_CONTENT,
    responses=_WRITE_ERRORS,
)
def delete_knockout_round(
    league_id: UUID,
    tournament_id: UUID,
    round_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> None:
    """Delete the newest round of a Lord have mercy knockout, with its results.

    The round is named by its id: an unknown one, a group round or a repeat is
    404 `round_not_found` (ADR-008). The fields let go of its matches, and
    the round before is unlocked, so a winner can change; drawing the round
    again gives the same pairs while the players are the same (FR-046, BR-146,
    BR-156). Deleting round 1 deletes the knockout (BR-087). A finished
    tournament is back in progress (BR-095), which recalculates the season
    standings (BR-112). 409: `season_closed` or `round_not_newest` (detail
    `round_id`, the newest round's). 422: `format_not_supported` (a
    fixed-pair knockout; detail `format`, `mode`).
    """
    remix_service.delete_knockout_round(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        round_id=round_id,
        user_id=user.id,
        clock=clock,
    )


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


@router.get("/bracket", responses=_REFUSED)
def read_bracket(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> BracketRead:
    """Return the knockout with its sides derived from the results (D4).

    A tournament without a knockout is 404 `knockout_not_found`; a Lord have
    mercy knockout, read with `…/knockout/rounds`, is 422 `format_not_supported`
    (detail `format`, `mode`).
    """
    bracket = knockout_service.read_bracket(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return BracketRead.model_validate(bracket)


@public_router.get("/bracket", responses=_REFUSED)
def read_public_bracket(
    share_token: str, tournament_id: UUID, session: SessionDep
) -> PublicBracketRead:
    """Return a tournament's knockout through the share link (FR-070).

    A tournament without a knockout is 404 `knockout_not_found`; a Lord have
    mercy knockout is 422 `format_not_supported`; one in setup is 404
    `tournament_not_found`, like an unknown one or one of another league.
    """
    bracket = knockout_service.read_shared_bracket(
        session, share_token=share_token, tournament_id=tournament_id
    )
    return PublicBracketRead.model_validate(bracket)


@public_router.get("/knockout/rounds", responses=_REFUSED)
def read_public_knockout_rounds(
    share_token: str, tournament_id: UUID, session: SessionDep
) -> PublicRemixKnockoutRead:
    """Return a Lord have mercy knockout round by round through the share link (FR-070).

    404 `knockout_not_found` without a knockout; one in setup is 404
    `tournament_not_found`, like an unknown one or one of another league. 422
    `format_not_supported` (detail `format`, `mode`) for a fixed-pair knockout.
    """
    knockout = remix_service.read_shared_knockout_rounds(
        session, share_token=share_token, tournament_id=tournament_id
    )
    return PublicRemixKnockoutRead.model_validate(knockout)
