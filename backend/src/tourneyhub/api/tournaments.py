from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter

from tourneyhub.api.deps import ClockDep, CurrentUserDep, SessionDep
from tourneyhub.api.schemas import ErrorResponse
from tourneyhub.api.tournament_models import (
    BackToSetupWrite,
    DrawWrite,
    FieldCreate,
    FieldRead,
    FinishWrite,
    HalvesWrite,
    MatchRead,
    PairsWrite,
    PlacementsWrite,
    PlaceRead,
    PlaceReasonRead,
    PlacesRead,
    PlayersWrite,
    PlayRead,
    PlayStandingRow,
    ResultWrite,
    RoundCreate,
    SchedulePreviewRead,
    SeedingWrite,
    SeedOrderWrite,
    StartWrite,
    SwissRoundRead,
    TiebreakersWrite,
    TopPlayersWrite,
    TournamentCreate,
    TournamentFormatWrite,
    TournamentRead,
    TournamentSetupRead,
    TournamentSummary,
    WaitingMatchRead,
)
from tourneyhub.engine.results import Game
from tourneyhub.services import tournaments as tournament_service
from tourneyhub.services.tournaments import (
    FieldPlacement,
    FormatRequest,
    MatchResult,
    PlacesView,
)

router = APIRouter(
    prefix="/leagues/{league_id}",
    tags=["tournaments"],
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND: {"model": ErrorResponse},
    },
)

_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    HTTPStatus.CONFLICT: {"model": ErrorResponse},
    HTTPStatus.UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}


@router.get("/seasons/{season_id}/tournaments")
def list_tournaments(
    league_id: UUID, season_id: UUID, session: SessionDep, user: CurrentUserDep
) -> list[TournamentSummary]:
    """List a season's tournaments, newest date first; closed seasons too (FR-022).

    Another league's season is 404 `season_not_found`.
    """
    tournaments = tournament_service.list_tournaments(
        session, league_id=league_id, season_id=season_id, user_id=user.id
    )
    return [TournamentSummary.model_validate(t) for t in tournaments]


@router.post("/tournaments", status_code=HTTPStatus.CREATED, responses=_WRITE_ERRORS)
def create_tournament(
    league_id: UUID,
    body: TournamentCreate,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Create a tournament in setup in the league's active season (FR-030).

    A repeat gets the tournament back. An id that another tournament has, in
    another season or with another type, is 409 `tournament_id_taken`. BO2 in a
    league without draws is 422 `draws_not_allowed` (BR-121). Points for sitting
    out in a round robin are 422 `sit_out_points_not_applicable` (BR-071).
    """
    setup = tournament_service.create_tournament(
        session,
        league_id=league_id,
        user_id=user.id,
        tournament_id=body.id,
        request=_format_request(body),
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.delete(
    "/tournaments/{tournament_id}",
    status_code=HTTPStatus.NO_CONTENT,
    responses={HTTPStatus.CONFLICT: {"model": ErrorResponse}},
)
def delete_tournament(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> None:
    """Delete a tournament with everything in it, in any state (FR-038).

    The UI asks first. A tournament of a closed season is 409 `season_closed`;
    a repeated delete is 404 `tournament_not_found`, which means it is gone.
    """
    tournament_service.delete_tournament(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )


@router.get("/tournaments/{tournament_id}")
def read_tournament(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> TournamentRead:
    """Return the whole tournament with its rounds and fields (FR-035, FR-092).

    Another league's tournament is 404 `tournament_not_found`.
    """
    tournament = tournament_service.read_tournament(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return TournamentRead.model_validate(tournament)


@router.post("/tournaments/{tournament_id}/start", responses=_WRITE_ERRORS)
def start_tournament(
    league_id: UUID,
    tournament_id: UUID,
    body: StartWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentRead:
    """Generate the schedule and start the tournament (FR-035).

    A round robin gets all its rounds (BR-050 to BR-052); a Swiss gets round
    1, the top half of the seeds against the bottom half, the lowest seed
    sitting out with an odd number (BR-055, BR-058), and adds the next rounds
    with `POST …/rounds`; a knockout without
    a group phase gets its whole bracket from the setup seeds, the byes for
    the top seeds (BR-040 to BR-044). The first matches take the fields
    (BR-130). A started tournament is 409 `tournament_not_in_setup`; a stale
    `expected_draw_counter` is 409 `draw_counter_changed`, and an
    `expected_seed_order` that is not the entries' current order, seed 1
    first, 409 `seed_order_changed`: the review shows the new setup. A Monster
    DYP gets round 1, groups of four by the league ranking with a top player
    leading each, the extra players sitting out (BR-060, BR-061, BR-063); its
    `expected_seed_order` is the preview's, the entries in league-ranking
    order. An incomplete setup is 422:
    `players_without_partner` (Doubles), `not_enough_players`,
    `dyp_halves_incomplete`, `dyp_halves_unequal`, `too_many_left_out` (DYP),
    `not_enough_entries` (FR-032: 2, 4 with a third-place match, 4 players
    in a Monster DYP),
    `too_many_entries_for_round_robin` (detail `limit`: 64) or
    `too_many_entries_for_knockout` (detail `limit`: 256).
    """
    tournament = tournament_service.start_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        expected_draw_counter=body.expected_draw_counter,
        expected_seed_order=body.expected_seed_order,
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


# The summary below is API text (openapi.json) and was left as it is: "until the
# first result". FR-036 and BR-096 say "while no match in the tournament has a
# result", which is also true again once every result is cleared (FR-053). The
# service already refuses on any result, so only the text changes, in the #48
# follow-up (issue to open after approval).
@router.post("/tournaments/{tournament_id}/back-to-setup", responses=_WRITE_ERRORS)
def back_to_setup(
    league_id: UUID,
    tournament_id: UUID,
    body: BackToSetupWrite,  # noqa: ARG001  (only "in_progress" validates)
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentRead:
    """Take a started tournament back to setup until the first result (FR-036).

    A tournament that is not in progress is 409 `tournament_not_in_progress`;
    one with a result is 422 `tournament_has_results`. The schedule goes; the
    entries, seeds and draws stay.
    """
    tournament = tournament_service.back_to_setup(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


@router.put("/tournaments/{tournament_id}/format", responses=_WRITE_ERRORS)
def set_tournament_format(
    league_id: UUID,
    tournament_id: UUID,
    body: TournamentFormatWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Set the format of a tournament in setup (FR-030, FR-031, FR-039).

    A new type keeps the picked players and makes the entries again. A started
    tournament is 409 `tournament_not_in_setup`, as for every setup write, so the
    points for sitting out cannot change while the phase has a result (BR-075).
    Points for sitting out in a round robin are 422
    `sit_out_points_not_applicable` (BR-071); BO2 in a league without draws, 422
    `draws_not_allowed` (BR-121).
    """
    setup = tournament_service.set_tournament_format(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        fmt=_format_request(body),
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.get("/tournaments/{tournament_id}/setup")
def read_tournament_setup(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> TournamentSetupRead:
    """Return a tournament's setup; another league's tournament is 404."""
    setup = tournament_service.read_tournament_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return TournamentSetupRead.model_validate(setup)


@router.put("/tournaments/{tournament_id}/setup/players", responses=_WRITE_ERRORS)
def set_tournament_players(
    league_id: UUID,
    tournament_id: UUID,
    body: PlayersWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Pick the tournament's players (FR-032).

    An id that is not a player of the league is 404 `player_not_found`; a
    removed player is 409 `player_removed` (BR-002): reload. A change makes the entries
    and draws again, and increments the draw counter (ADR-010).
    """
    setup = tournament_service.set_tournament_players(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        player_ids=body.player_ids,
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.put("/tournaments/{tournament_id}/setup/pairs", responses=_WRITE_ERRORS)
def set_doubles_pairs(
    league_id: UUID,
    tournament_id: UUID,
    body: PairsWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Set a Doubles tournament's pairs (FR-033, BR-003, BR-030).

    A player who is not picked is 409 `player_not_picked`; a tournament of
    another type is 409 `tournament_type_changed`. Reload on both.
    """
    setup = tournament_service.set_doubles_pairs(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        pairs=body.pairs,
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.put("/tournaments/{tournament_id}/setup/halves", responses=_WRITE_ERRORS)
def set_dyp_halves(
    league_id: UUID,
    tournament_id: UUID,
    body: HalvesWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Make a DYP tournament's halves by ranking or by hand (FR-033, BR-032).

    Once every picked player has a half and the halves are equal, with at most
    one left out, the partners are drawn (BR-033). 409 `player_not_picked` and
    `tournament_type_changed` as for pairs.
    """
    setup = tournament_service.set_dyp_halves(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        method=body.method,
        halves={half.player_id: half.half for half in body.halves},
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.put("/tournaments/{tournament_id}/setup/top-players", responses=_WRITE_ERRORS)
def set_top_players(
    league_id: UUID,
    tournament_id: UUID,
    body: TopPlayersWrite,
    session: SessionDep,
    user: CurrentUserDep,
) -> TournamentSetupRead:
    """Mark the Monster DYP top players, the target state (FR-041, BR-061).

    At most one per match of round 1: 422 `too_many_top_players` with `max`;
    409 `player_not_picked` for a player who is not in the tournament. Other
    types: 409 `tournament_type_changed`.
    """
    setup = tournament_service.set_top_players(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        player_ids=body.player_ids,
    )
    return TournamentSetupRead.model_validate(setup)


@router.put("/tournaments/{tournament_id}/setup/seeding", responses=_WRITE_ERRORS)
def set_seeding_method(
    league_id: UUID,
    tournament_id: UUID,
    body: SeedingWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Seed by league ranking or by random shuffle (FR-034).

    Monster DYP has no seeds: 409 `tournament_type_changed`.
    """
    setup = tournament_service.set_seeding_method(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        method=body.method,
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.put("/tournaments/{tournament_id}/setup/seed-order", responses=_WRITE_ERRORS)
def set_seed_order(
    league_id: UUID,
    tournament_id: UUID,
    body: SeedOrderWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Reorder the seeds by hand (FR-034).

    An order that does not list exactly the current entries is 409
    `seed_order_changed`: reload.
    """
    setup = tournament_service.set_seed_order(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        entry_ids=body.entry_ids,
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.get("/tournaments/{tournament_id}/setup/preview")
def read_schedule_preview(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> SchedulePreviewRead:
    """Return what "Generate and start" would create, and write nothing (FR-035).

    A tournament that cannot start is still 200 with `can_start` false and the
    `problem`: `players_without_partner`, `not_enough_entries`,
    `too_many_entries_for_round_robin` (detail `limit`: 64),
    `too_many_entries_for_knockout` (detail `limit`: 256),
    the DYP codes of a draw that cannot be made, or
    `tournament_not_in_setup` for a started tournament. Another league's
    tournament is 404.
    """
    preview = tournament_service.preview_schedule(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return SchedulePreviewRead.model_validate(preview)


@router.post("/tournaments/{tournament_id}/setup/draw", responses=_WRITE_ERRORS)
def draw_again(
    league_id: UUID,
    tournament_id: UUID,
    body: DrawWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Draw again: a new DYP draw, the rest of Doubles paired, or a shuffle (ADR-010).

    A stale `expected_draw_counter` is 409 `draw_counter_changed` with the
    current `draw_counter`. Shuffling seeds that come from the ranking is 409
    `seeding_method_changed`. A DYP draw needs complete, valid halves: 422
    `dyp_halves_incomplete`, `dyp_halves_unequal`, `too_many_left_out` or
    `not_enough_players`. Pairing the rest of Doubles with fewer than two
    unpaired players is 422 `nothing_to_pair`; nothing changes.
    """
    setup = tournament_service.draw_again(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        target=body.target,
        expected_draw_counter=body.expected_draw_counter,
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.put(
    "/tournaments/{tournament_id}/matches/{match_id}/result", responses=_WRITE_ERRORS
)
def set_match_result(
    league_id: UUID,
    tournament_id: UUID,
    match_id: UUID,
    body: ResultWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> MatchRead:
    """Enter, replace or clear a match's result (FR-050 to FR-053, FR-094).

    The body is the whole result, so a repeat changes nothing (ADR-008).
    Entering one frees the match's field, which takes the next waiting match
    (BR-130, BR-131). The empty result clears it: the match waits again, not
    put back on its old field (BR-134), and a finished tournament is back in
    progress (BR-095). The free fields are then filled, so the first match that
    can be played takes one, the cleared match included.

    A closed season is 409 `season_closed`. An unknown match is 404
    `match_not_found`. A match whose sides are not both known is 422
    `match_sides_unknown` (BR-091). A result that breaks a rule is 422:
    `result_does_not_fit_format` (BR-121, detail `format` and `games`),
    `draws_not_allowed` (BR-090), `game_score_mismatch` (BR-092, detail
    `game_no`) or `scores_required` (Swiss and Monster DYP, detail `game_no`).
    A walkover with games is 422 `validation_failed`.

    A knockout match after the first round has derived sides: the body names
    the entries the screen saw in `expected_sides`. Other entries, or a side
    still to come, are 409 `match_sides_changed` (detail `entry_ids`, the
    current ones); none is 422 `expected_sides_required`.

    The knockout: once it is drawn, a group-phase result is 422
    `group_phase_locked` (BR-053, detail `phase_id`); a knockout result that a
    later match it feeds has a result for is 422 `result_locked` (BR-094,
    detail `match_ids`), and a knockout has no draws (BR-090). A new winner
    changes the later matches' sides. The result that completes the
    knockout finishes the tournament (FR-037). In a Swiss, a result of a
    round before the newest is 422 `round_locked` (BR-065, detail
    `round_no`, the newest round's); deleting the newest round unlocks it
    (BR-066).
    """
    match = tournament_service.set_match_result(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        match_id=match_id,
        user_id=user.id,
        result=MatchResult(
            expected_sides=body.expected_sides,
            walkover_winner=body.walkover_winner,
            games=tuple(
                Game(winner=game.winner, score_1=game.score_1, score_2=game.score_2)
                for game in body.games
            ),
        ),
        clock=clock,
    )
    return MatchRead.model_validate(match)


@router.get("/tournaments/{tournament_id}/play")
def read_play(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> PlayRead:
    """Return the waiting list, the live standings and whether the group phase is done.

    Computed on read (FR-040, FR-060, FR-092). Another league's tournament is
    404 `tournament_not_found`.
    """
    play = tournament_service.read_play(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return PlayRead(
        waiting=[WaitingMatchRead.model_validate(match) for match in play.waiting],
        standings=[PlayStandingRow.model_validate(row) for row in play.standings],
        group_done=play.group_done,
    )


@router.post(
    "/tournaments/{tournament_id}/rounds",
    status_code=HTTPStatus.CREATED,
    responses=_WRITE_ERRORS,
)
def add_round(
    league_id: UUID,
    tournament_id: UUID,
    body: RoundCreate,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> SwissRoundRead:
    """Draw the next round of a Swiss or Monster DYP from the standings (FR-040, FR-042).

    A Swiss: entries play their neighbour in the standings without meeting
    anyone twice while that can be avoided (BR-056, BR-057, ADR-011); with an
    odd number one sits out (BR-058). A Monster DYP: players are grouped in
    fours by their standing, the 1st and 4th against the 2nd and 3rd, with the
    top players of the league ranking apart in rounds 1 and 2 and nobody
    getting a partner twice while that can be avoided (BR-060 to BR-062); the
    extra one to three players sit out (BR-063). Disabled entries are not
    drawn (BR-064). The rounds before it lock (BR-065), and its first matches
    take the free fields (BR-130). Returns the new round, with what a lot
    decided and which pairs repeat (ADR-009).

    409: `round_number_changed` (the body's `expected_round_no` is not the
    newest round's number plus one; detail `current_round_no`, the newest
    round's), `tournament_not_in_progress` (detail `state`) or
    `season_closed`. 422: `format_not_supported` (not a Swiss or Monster DYP;
    detail `format`), `group_phase_locked` (the knockout is drawn; detail
    `phase_id`), `round_not_complete` (a match of the newest round has no
    result; detail `matches_left`), `not_enough_entries` (a Swiss with fewer
    than 2 entries that are not disabled) or `not_enough_players` (a Monster
    DYP with fewer than 4 players that are not disabled; details `minimum`,
    `given`).
    """
    round_ = tournament_service.add_round(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        expected_round_no=body.expected_round_no,
        clock=clock,
    )
    return SwissRoundRead.model_validate(round_)


@router.delete(
    "/tournaments/{tournament_id}/rounds/{round_id}",
    status_code=HTTPStatus.NO_CONTENT,
    responses=_WRITE_ERRORS,
)
def delete_round(
    league_id: UUID,
    tournament_id: UUID,
    round_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> None:
    """Delete the newest round of a Swiss or Monster DYP, with its results (FR-046).

    The UI asks first.

    The round before it unlocks (BR-066). Deleting round 1 takes the
    tournament back to setup, results or not: every round goes, the
    entries, seeds, draws and top-player marks stay, and every disabled flag
    is cleared.

    An unknown round, or a repeated delete, is 404 `round_not_found`: it is
    gone. 409: `round_not_newest` (a later round exists; detail `round_id`,
    the newest round's), `tournament_not_in_progress` (detail `state`) or
    `season_closed`. 422: `format_not_supported` (not a Swiss or Monster DYP;
    detail `format`) or `group_phase_locked` (the knockout is drawn: delete it
    first, BR-087; detail `phase_id`).
    """
    tournament_service.delete_round(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        round_id=round_id,
        user_id=user.id,
        clock=clock,
    )


@router.put("/tournaments/{tournament_id}/tiebreakers", responses=_WRITE_ERRORS)
def set_tiebreakers(
    league_id: UUID,
    tournament_id: UUID,
    body: TiebreakersWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentRead:
    """Set the tie-breakers of a Swiss or Monster DYP and their order (FR-043, BR-072).

    Allowed in setup and while the tournament runs; the standings of
    `GET …/play` follow at once, since they are computed on read. Returns the
    whole tournament, whose group phase carries the new `tiebreakers`.

    409: `tournament_not_in_progress` (the tournament is finished; detail
    `state`) or `season_closed`. 422: `format_not_supported` (not a Swiss or a
    Monster DYP; detail `format`) or `group_phase_locked` (the knockout is
    drawn, so the group standing is fixed; detail `phase_id`).
    """
    tournament = tournament_service.set_tiebreakers(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        tiebreakers=body.tiebreakers,
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


@router.post(
    "/tournaments/{tournament_id}/fields",
    status_code=HTTPStatus.CREATED,
    responses=_WRITE_ERRORS,
)
def add_field(
    league_id: UUID,
    tournament_id: UUID,
    body: FieldCreate,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> FieldRead:
    """Add a field while the tournament runs (FR-090, BR-132).

    The body carries the number the field expects to get, the lowest free
    one. The new field takes the next waiting match at once; `match_id` is
    null when no waiting match can be played.

    A tournament in setup or finished is 409 `tournament_not_in_progress`
    (detail `state`); setup sets the number of fields with the format. Any
    other number, a repeat included, is 409 `field_number_changed` with the
    `number` a new field would get now, null when all 32 are taken.
    """
    field = tournament_service.add_field(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        number=body.number,
        clock=clock,
    )
    return FieldRead.model_validate(field)


@router.delete(
    "/tournaments/{tournament_id}/fields/{field_id}",
    status_code=HTTPStatus.NO_CONTENT,
    responses=_WRITE_ERRORS,
)
def remove_field(
    league_id: UUID,
    tournament_id: UUID,
    field_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> None:
    """Remove a field while the tournament runs; the UI asks first (FR-090, BR-132).

    The other fields keep their numbers. The match on the removed field goes
    to the front of the waiting list, so it takes the next field that frees
    up, or a free one at once.

    An unknown field, or a repeated delete, is 404 `field_not_found`: the
    field is gone. A tournament not in progress is 409
    `tournament_not_in_progress`. The last field is 422 `last_field`.
    """
    tournament_service.remove_field(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        field_id=field_id,
        user_id=user.id,
        clock=clock,
    )


@router.put("/tournaments/{tournament_id}/fields/placements", responses=_WRITE_ERRORS)
def place_matches(
    league_id: UUID,
    tournament_id: UUID,
    body: PlacementsWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentRead:
    """Place, move, swap or take off matches by hand (FR-093, BR-133).

    Each named match ends on its named field, or waiting, from the field the
    screen saw it on (`from_field_id`). A placement by hand holds until the
    match has a result. A field a match leaves takes the next waiting match,
    but not one this request sends back to waiting, which waits in schedule
    order. Returns the whole
    tournament with its fields and waiting list.

    An unknown match is 404 `match_not_found`, an unknown field 404
    `field_not_found`. A stale screen gets 409: `tournament_not_in_progress`,
    `match_has_result` (detail `match_id`), `placement_changed` (a match is not
    on the `from_field_id` any more) or `field_not_free` (another match is on
    the field now; detail `field_id`, `match_id`). A match whose sides are not
    both known, or with a bye, is 422 `match_sides_unknown` (BR-091). Anything
    but the four operations of FR-093 (replacing the match on a field, a
    rotation) is 422 `placement_not_allowed`.
    A player who would be on two fields at once is 422
    `player_on_another_field` (BR-131; detail `player_ids`, and `field_ids`,
    the fields that would hold them, lowest number first).
    """
    tournament = tournament_service.place_matches(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        placements=[
            FieldPlacement(
                match_id=p.match_id,
                field_id=p.field_id,
                from_field_id=p.from_field_id,
            )
            for p in body.placements
        ],
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


@router.post("/tournaments/{tournament_id}/finish", responses=_WRITE_ERRORS)
def finish_tournament(
    league_id: UUID,
    tournament_id: UUID,
    body: FinishWrite,  # noqa: ARG001  (only "in_progress" validates)
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentRead:
    """Finish a round robin, Swiss or Monster DYP without a knockout (FR-040).

    The UI asks first.

    A tournament that is not in progress is 409 `tournament_not_in_progress`
    (detail `state`), so a repeat changes nothing. A match without a result is
    422 `group_phase_not_done` (detail `matches_left`). A tournament with a
    knockout, which finishes with its last result (FR-037), is 422
    `format_not_supported`.
    The standings become the places (`GET …/places`).
    """
    tournament = tournament_service.finish_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


@router.get(
    "/tournaments/{tournament_id}/places",
    responses={HTTPStatus.UNPROCESSABLE_CONTENT: {"model": ErrorResponse}},
)
def read_places(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> PlacesRead:
    """Return the places and the season points of a finished tournament (§7.13, §7.14).

    Computed on read. Before the tournament finishes, `complete` is false and
    there are no rows. With a knockout, its entries take the top places and
    the others follow in their group-phase order (BR-102, BR-103); without a
    group phase, every entry is placed by the knockout, and its reason has no
    `group_place` and no `group_format`. A Monster DYP is 422
    `format_not_supported` until it is played.
    """
    places = tournament_service.read_places(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return places_read(places)


def places_read(places: PlacesView) -> PlacesRead:
    """The places as the API answers them; the organizer's and the viewers' alike."""
    return PlacesRead(
        complete=places.complete,
        rows=[
            PlaceRead(
                place=row.place,
                entry_id=row.entry_id,
                points_per_player=row.points_per_player,
                reason=PlaceReasonRead(
                    kind=row.kind,
                    round=row.round,
                    score=row.score,
                    opponent_entry_id=row.opponent_entry_id,
                    group_place=row.group_place,
                    group_format=places.group_format,
                ),
            )
            for row in places.rows
        ],
    )


def _format_request(body: TournamentFormatWrite | TournamentCreate) -> FormatRequest:
    return FormatRequest(
        name=body.name,
        date=body.date,
        type=body.type,
        group_phase=body.group_phase,
        round_robin_legs=body.round_robin_legs,
        sit_out_points=body.sit_out_points,
        group_match_format=body.group_match_format,
        knockout_match_format=body.knockout_match_format,
        final_match_format=body.final_match_format,
        third_place_match=body.third_place_match,
        goals_per_game=body.goals_per_game,
        field_count=body.field_count,
    )
