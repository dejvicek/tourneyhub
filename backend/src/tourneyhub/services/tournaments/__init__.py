"""Tournaments: setup, start, results, fields, standings and finishing (FR-030 to FR-094).

Every write locks the league row, then the tournament row (ADR-008), and loads
every id it is given through them. A change to the entries discards the seeding
and draws again where the inputs are complete, incrementing the draw counter
(ADR-010). Starting creates the schedule with the engine and puts the first
matches on the fields (FR-035, BR-130); going back to setup deletes it while no
match has a result (FR-036). Results and placements by hand are whole target
states (ADR-008); the standings and places are computed on read (ADR-009).
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.errors import EngineError
from tourneyhub.engine.ids import EntryId
from tourneyhub.engine.swiss import draw_next_swiss_round
from tourneyhub.engine.tournaments import PhaseFormat, Tiebreaker, TournamentState
from tourneyhub.errors import (
    ConflictError,
    ErrorCode,
    NotFoundError,
    RuleViolationError,
)
from tourneyhub.services.engine_errors import to_app_error
from tourneyhub.services.tournaments.entries import (
    DrawTarget,
    draw_again,
    set_doubles_pairs,
    set_dyp_halves,
    set_seed_order,
    set_seeding_method,
    set_tournament_players,
)
from tourneyhub.services.tournaments.fields import (
    FieldPlacement,
    _fill_fields,
    add_field,
    place_matches,
    remove_field,
)
from tourneyhub.services.tournaments.places import (
    PlacesView,
    finished_season_points,
    read_places,
    view_places,
)
from tourneyhub.services.tournaments.play import (
    GroupStandingRow,
    _swiss_rounds,
    _swiss_standings_of,
    group_standings,
    read_play,
    tie_groups,
    view_group_standings,
)
from tourneyhub.services.tournaments.results import MatchResult, set_match_result
from tourneyhub.services.tournaments.setup import (
    FormatRequest,
    create_tournament,
    delete_tournament,
    set_tournament_format,
)
from tourneyhub.services.tournaments.shared import (
    PLAYED_GROUP_FORMATS,
    ROUND_BY_ROUND_FORMATS,
    Clock,
    KnockoutBracket,
    _group_phase,
    _lock_tournament,
    _main_entries,
    _match_slots,
    _played,
    _require_open_season,
    knockout_bracket,
)
from tourneyhub.services.tournaments.start import (
    _insert_schedule,
    _reset_to_setup,
    _schedule_rows,
    _swiss_round_of,
    back_to_setup,
    preview_schedule,
    start_tournament,
)
from tourneyhub.services.tournaments.views import (
    DrawnMatchView,
    DrawnRoundView,
    SideView,
    TournamentSummary,
    TournamentView,
    list_season_tournaments,
    list_tournaments,
    read_tournament,
    read_tournament_setup,
    view_tournament,
)

__all__ = [
    "PLAYED_GROUP_FORMATS",
    "Clock",
    "DrawTarget",
    "FieldPlacement",
    "FormatRequest",
    "GroupStandingRow",
    "KnockoutBracket",
    "MatchResult",
    "PlacesView",
    "SideView",
    "TournamentSummary",
    "TournamentView",
    "add_field",
    "back_to_setup",
    "create_tournament",
    "delete_tournament",
    "draw_again",
    "finished_season_points",
    "group_standings",
    "knockout_bracket",
    "list_season_tournaments",
    "list_tournaments",
    "place_matches",
    "preview_schedule",
    "read_places",
    "read_play",
    "read_tournament",
    "read_tournament_setup",
    "remove_field",
    "set_doubles_pairs",
    "set_dyp_halves",
    "set_match_result",
    "set_seed_order",
    "set_seeding_method",
    "set_tournament_format",
    "set_tournament_players",
    "start_tournament",
    "tie_groups",
    "view_group_standings",
    "view_places",
    "view_tournament",
]


def _require_swiss(tournament: Tournament) -> TournamentPhase:
    """The Swiss group phase whose rounds are added and deleted (FR-040, FR-046).

    Any other group phase, or none, is 422 `format_not_supported` (detail
    `format`); Monster DYP rounds come later.
    """
    group = _group_phase(tournament)
    if group is None or group.format is not PhaseFormat.SWISS:
        format_ = tournament.phases[0].format if group is None else group.format
        raise RuleViolationError(ErrorCode.FORMAT_NOT_SUPPORTED, format=format_)
    return group


def _require_no_knockout(tournament: Tournament) -> None:
    """Refuse a change to the group phase once the knockout is drawn (BR-053).

    422 `group_phase_locked` with the knockout's `phase_id`; deleting the
    knockout unlocks it (BR-087).
    """
    knockout = knockout_bracket(tournament)
    if knockout is not None:
        raise RuleViolationError(
            ErrorCode.GROUP_PHASE_LOCKED, phase_id=str(knockout.phase.id)
        )


def add_round(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    expected_round_no: int,
    clock: Clock,
) -> DrawnRoundView:
    """Draw the next round of a Swiss from the standings (FR-040, FR-042).

    The request carries the number the new round expects, the newest round's
    plus one: any other is 409 `round_number_changed` (detail
    `current_round_no`, the newest round's), so a repeat draws nothing
    (ADR-008). A closed season is 409 `season_closed`, a tournament not in
    progress 409 `tournament_not_in_progress`. A group phase that is not a
    Swiss is 422 `format_not_supported`; once the knockout is drawn, 422
    `group_phase_locked`. A match of the newest round without a result is 422
    `round_not_complete` (detail `matches_left`), and fewer than 2 entries
    that are not disabled 422 `not_enough_entries`.

    The round is drawn from the standings over every stored round (BR-056 to
    BR-058, ADR-011), leaving out disabled entries, whose participation is
    `disabled` (BR-064). The rounds before it are locked from now on
    (BR-065), and its first matches take the free fields (BR-130). The round
    comes back with what a lot decided and which pairs repeat (ADR-009).
    """
    league, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    _require_open_season(league, tournament)
    if tournament.state is not TournamentState.IN_PROGRESS:
        raise ConflictError(
            ErrorCode.TOURNAMENT_NOT_IN_PROGRESS, state=tournament.state
        )
    group = _require_swiss(tournament)
    _require_no_knockout(tournament)
    newest = group.rounds[-1]  # a running Swiss has round 1 (FR-046)
    if expected_round_no != newest.round_no + 1:
        raise ConflictError(
            ErrorCode.ROUND_NUMBER_CHANGED, current_round_no=newest.round_no
        )
    left = sum(match.outcome is None for match in _played(newest))
    if left:
        raise RuleViolationError(ErrorCode.ROUND_NOT_COMPLETE, matches_left=left)
    main = _main_entries(tournament)
    disabled = {EntryId(entry.id) for entry in main if entry.is_disabled}
    try:
        draw = draw_next_swiss_round(
            _swiss_standings_of(tournament, group),
            _swiss_rounds(group),
            disabled=sorted(disabled),
        )
    except EngineError as err:
        raise to_app_error(err) from err
    now = clock()
    members = {
        entry.id: sorted(member.player_id for member in entry.members) for entry in main
    }
    rows = _schedule_rows(
        group, [_swiss_round_of(draw)], members, now, disabled=disabled
    )
    _insert_schedule(session, rows)  # the matches exist before a field references one
    tournament.updated_at = now
    _fill_fields(tournament, [*_match_slots(tournament), *rows.slots], now)
    session.flush()
    round_id = rows.rounds[0]["id"]
    view = read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )
    round_ = next(round_ for round_ in view.rounds if round_.id == round_id)
    # The schedule rows number the matches in the order of the pairs, from 1.
    pairs = dict(enumerate(draw.pairs, start=1))
    return DrawnRoundView(
        id=round_.id,
        phase_id=round_.phase_id,
        round_no=round_.round_no,
        matches=tuple(
            DrawnMatchView(
                id=match.id,
                round_id=match.round_id,
                position=match.position,
                kind=match.kind,
                sides=match.sides,
                outcome=match.outcome,
                is_walkover=match.is_walkover,
                games=match.games,
                result_entered_at=match.result_entered_at,
                is_repeat=pairs[match.position].is_repeat,
                is_decided_by_lot=pairs[match.position].is_decided_by_lot,
            )
            for match in round_.matches
        ),
        sitting_out=round_.sitting_out,
        is_sit_out_by_lot=draw.is_sit_out_by_lot,
    )


def delete_round(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    round_id: UUID,
    user_id: UUID,
    clock: Clock,
) -> None:
    """Delete the newest round of a Swiss, with any results in it (FR-046, BR-066).

    The round is named by its id (ADR-008): an unknown one, one of another
    tournament or a repeated delete is 404 `round_not_found`. A closed season
    is 409 `season_closed`, a tournament not in progress 409
    `tournament_not_in_progress`. A round of another group format is 422
    `format_not_supported`; once the knockout is drawn, 422
    `group_phase_locked` (delete the knockout first, BR-087). A round that is
    not the newest is 409 `round_not_newest` (detail `round_id`, the newest
    round's).

    The fields let go of its matches, and its matches and participation go
    with it; the round before it is unlocked (BR-066), since the newest round
    is found on every write. Deleting round 1 takes the tournament back to
    setup, as "back to setup" does but with results allowed (FR-036, FR-046):
    every round goes, the entries, seeds and draws stay, and every disabled
    flag is cleared. Late entries, which would become ordinary entries of the
    setup and be drawn again (DATA-MODEL §4.5), come with P14.
    """
    league, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    _require_open_season(league, tournament)
    group = _group_phase(tournament)
    round_ = next(
        (r for r in ([] if group is None else group.rounds) if r.id == round_id),
        None,
    )
    if group is None or round_ is None:
        raise NotFoundError(ErrorCode.ROUND_NOT_FOUND)
    if tournament.state is not TournamentState.IN_PROGRESS:
        raise ConflictError(
            ErrorCode.TOURNAMENT_NOT_IN_PROGRESS, state=tournament.state
        )
    _require_swiss(tournament)
    _require_no_knockout(tournament)
    newest = group.rounds[-1]
    if round_ is not newest:
        raise ConflictError(ErrorCode.ROUND_NOT_NEWEST, round_id=str(newest.id))
    now = clock()
    if round_.round_no == 1:
        _reset_to_setup(session, tournament, now)
        return
    matches = {match.id for match in round_.matches}
    for field in tournament.fields:
        if field.match_id in matches:
            field.match_id = None
            field.updated_at = now
    session.flush()  # the fields let go of the matches before they are deleted
    group.rounds.remove(round_)
    tournament.updated_at = now
    session.flush()  # the matches are gone before the free fields take the next ones
    _fill_fields(tournament, _match_slots(tournament), now)
    session.flush()


def set_tiebreakers(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    tiebreakers: Sequence[Tiebreaker],
    clock: Clock,
) -> TournamentView:
    """Set which tie-breakers a Swiss or Monster DYP uses, in order (FR-043, BR-072).

    The target state: the enabled tie-breakers, first one first; an empty
    list orders entries level on points by lot alone (BR-074). A repeat
    changes nothing (ADR-008). Allowed in setup and while the tournament runs,
    since the standings are computed on read (ADR-009). A finished tournament
    is 409 `tournament_not_in_progress`, a closed season 409 `season_closed`.
    A group phase that is not a Swiss or a Monster DYP, or none, is 422
    `format_not_supported`; once the knockout is drawn the group standing is
    fixed, 422 `group_phase_locked` (BR-053).
    """
    league, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    _require_open_season(league, tournament)
    if tournament.state is TournamentState.FINISHED:
        raise ConflictError(
            ErrorCode.TOURNAMENT_NOT_IN_PROGRESS, state=tournament.state
        )
    group = _group_phase(tournament)
    if group is None or group.format not in ROUND_BY_ROUND_FORMATS:
        format_ = tournament.phases[0].format if group is None else group.format
        raise RuleViolationError(ErrorCode.FORMAT_NOT_SUPPORTED, format=format_)
    _require_no_knockout(tournament)
    if group.tiebreakers != list(tiebreakers):
        now = clock()
        group.tiebreakers = list(tiebreakers)
        group.updated_at = now
        tournament.updated_at = now
        session.flush()
    return read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )


def _require_group_only(tournament: Tournament) -> TournamentPhase:
    """The round robin or Swiss of a tournament without a knockout (FR-040).

    A knockout finishes by itself (FR-037), and Monster DYP is not played
    yet: 422 `format_not_supported` until it is.
    """
    group = _group_phase(tournament)
    last = tournament.phases[-1]
    if group is not last or group.format not in PLAYED_GROUP_FORMATS:
        raise RuleViolationError(ErrorCode.FORMAT_NOT_SUPPORTED, format=last.format)
    return group


def finish_tournament(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    clock: Clock,
) -> TournamentView:
    """Finish a round robin or a Swiss without a knockout; the UI asks first (FR-040).

    The request expects the tournament in progress; in any other state it is
    409 `tournament_not_in_progress`, so a repeat changes nothing (ADR-008). A
    match still without a result is 422 `group_phase_not_done` (detail
    `matches_left`). The standings become the places, and the places earn
    season points; both are computed on read (`read_places`, D1).
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
    group = _require_group_only(tournament)
    left = sum(
        match.outcome is None for round_ in group.rounds for match in _played(round_)
    )
    if left:
        raise RuleViolationError(ErrorCode.GROUP_PHASE_NOT_DONE, matches_left=left)
    tournament.state = TournamentState.FINISHED
    tournament.updated_at = clock()
    session.flush()
    return read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )
