"""Swiss and Monster DYP rounds, tie-breakers and finishing a group-only tournament."""

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
from tourneyhub.services.tournaments.fields import _fill_fields
from tourneyhub.services.tournaments.monster_dyp import (
    draw_monster,
    monster_schedule_rows,
)
from tourneyhub.services.tournaments.places import _current_ranking
from tourneyhub.services.tournaments.play import (
    _player_of,
    _swiss_rounds,
    _swiss_standings_of,
)
from tourneyhub.services.tournaments.shared import (
    PLAYED_GROUP_FORMATS,
    ROUND_BY_ROUND_FORMATS,
    Clock,
    _group_phase,
    _insert_schedule,
    _lock_tournament,
    _main_entries,
    _match_slots,
    _played,
    _require_open_season,
    _ScheduleRows,
    knockout_bracket,
)
from tourneyhub.services.tournaments.start import (
    _reset_to_setup,
    _schedule_rows,
    _swiss_round_of,
)
from tourneyhub.services.tournaments.views import (
    DrawnMatchView,
    DrawnRoundView,
    TournamentView,
    read_tournament,
)


def _require_round_by_round(tournament: Tournament) -> TournamentPhase:
    """The Swiss or Monster DYP group phase whose rounds are added and deleted.

    Any other group phase, or none, is 422 `format_not_supported` (detail
    `format`; FR-040, FR-046).
    """
    group = _group_phase(tournament)
    if group is None or group.format not in ROUND_BY_ROUND_FORMATS:
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
    """Draw the next round of a Swiss or Monster DYP from the standings (FR-040, FR-042).

    The request carries the number the new round expects, the newest round's
    plus one: any other is 409 `round_number_changed` (detail
    `current_round_no`, the newest round's), so a repeat draws nothing
    (ADR-008). A closed season is 409 `season_closed`, a tournament not in
    progress 409 `tournament_not_in_progress`. A group phase that is not a
    Swiss or a Monster DYP is 422 `format_not_supported`; once the knockout is
    drawn, 422 `group_phase_locked`. A match of the newest round without a
    result is 422 `round_not_complete` (detail `matches_left`). Fewer than 2
    entries that are not disabled in a Swiss is 422 `not_enough_entries`,
    fewer than 4 players in a Monster DYP 422 `not_enough_players`.

    A Swiss round is drawn from the standings over every stored round (BR-056
    to BR-058, ADR-011). A Monster DYP round groups the players in fours by
    their standing (BR-060); in rounds 1 and 2 the top players come from the
    league ranking of now (BR-061, BR-020), and nobody gets a partner twice
    while that can be avoided (BR-062, ADR-011). Disabled entries are left
    out, with participation `disabled` (BR-064). The rounds before it are
    locked from now on (BR-065), and its first matches take the free fields
    (BR-130). The round comes back with what a lot decided and which pairs
    repeat (ADR-009); in a Monster DYP a match is a repeat when a forced
    repeated partner is in it, and the lot of a match is the draw's.
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
    group = _require_round_by_round(tournament)
    _require_no_knockout(tournament)
    newest = group.rounds[-1]  # a running Swiss or Monster DYP has round 1 (FR-046)
    if expected_round_no != newest.round_no + 1:
        raise ConflictError(
            ErrorCode.ROUND_NUMBER_CHANGED, current_round_no=newest.round_no
        )
    left = sum(match.outcome is None for match in _played(newest))
    if left:
        raise RuleViolationError(ErrorCode.ROUND_NOT_COMPLETE, matches_left=left)
    main = _main_entries(tournament)
    now = clock()
    marks: list[tuple[bool, bool]]  # per match: (is_repeat, is_decided_by_lot)
    if group.format is PhaseFormat.MONSTER_DYP:
        monster = draw_monster(
            tournament,
            group,
            ranking=_current_ranking(session, league=league, tournament=tournament),
        )
        rows = monster_schedule_rows(
            group, monster, {_player_of(entry): entry.id for entry in main}, now
        )
        marks = [
            (g.is_team_1_repeat or g.is_team_2_repeat, monster.is_grouping_by_lot)
            for g in monster.groups
        ]
        is_sit_out_by_lot = monster.is_sit_out_by_lot
    else:
        disabled = {EntryId(entry.id) for entry in main if entry.is_disabled}
        try:
            draw = draw_next_swiss_round(
                _swiss_standings_of(tournament, group),
                _swiss_rounds(group),
                disabled=sorted(disabled),
            )
        except EngineError as err:
            raise to_app_error(err) from err
        members = {
            entry.id: sorted(member.player_id for member in entry.members)
            for entry in main
        }
        rows = _schedule_rows(
            group, [_swiss_round_of(draw)], members, now, disabled=disabled
        )
        marks = [(pair.is_repeat, pair.is_decided_by_lot) for pair in draw.pairs]
        is_sit_out_by_lot = draw.is_sit_out_by_lot
    _insert_schedule(session, rows)  # the matches exist before a field references one
    tournament.updated_at = now
    _fill_fields(tournament, [*_match_slots(tournament), *rows.slots], now)
    session.flush()
    return _drawn_round(
        session,
        rows,
        marks,
        is_sit_out_by_lot=is_sit_out_by_lot,
        league_id=league_id,
        tournament_id=tournament.id,
        user_id=user_id,
    )


def _drawn_round(
    session: Session,
    rows: _ScheduleRows,
    marks: Sequence[tuple[bool, bool]],
    *,
    is_sit_out_by_lot: bool,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
) -> DrawnRoundView:
    """The stored round with what a lot decided, from the draw's own marks."""
    round_id = rows.rounds[0]["id"]
    view = read_tournament(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    round_ = next(round_ for round_ in view.rounds if round_.id == round_id)
    # The schedule rows number the matches in the order of the draw, from 1.
    by_position = dict(enumerate(marks, start=1))
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
                is_repeat=by_position[match.position][0],
                is_decided_by_lot=by_position[match.position][1],
            )
            for match in round_.matches
        ),
        sitting_out=round_.sitting_out,
        is_sit_out_by_lot=is_sit_out_by_lot,
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
    """Delete the newest round of a Swiss or Monster DYP, with its results (FR-046, BR-066).

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
    every round goes, the entries, seeds, draws and top-player marks stay, and
    every disabled flag is cleared. Late entries, which would become ordinary entries of the
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
    _require_round_by_round(tournament)
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
    """The round robin, Swiss or Monster DYP of a tournament without a knockout (FR-040).

    A knockout finishes by itself (FR-037): 422 `format_not_supported`. The
    shared `PLAYED_GROUP_FORMATS` leaves Monster DYP out, so it is added here.
    """
    group = _group_phase(tournament)
    last = tournament.phases[-1]
    allowed = PLAYED_GROUP_FORMATS | {PhaseFormat.MONSTER_DYP}
    if group is not last or group.format not in allowed:
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
    """Finish a round robin, Swiss or Monster DYP without a knockout (FR-040).

    The UI asks first.

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
