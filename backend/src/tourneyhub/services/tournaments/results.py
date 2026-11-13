"""Entering and clearing match results."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League
from tourneyhub.db.models.matches import Match, MatchGame, Round
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.errors import EngineError
from tourneyhub.engine.knockout import is_complete, locked_by
from tourneyhub.engine.results import Game, match_outcome
from tourneyhub.engine.tournaments import (
    MatchFormat,
    MatchKind,
    Outcome,
    PhaseFormat,
    PhaseKind,
    TournamentState,
)
from tourneyhub.errors import ConflictError, ErrorCode, RuleViolationError
from tourneyhub.services.engine_errors import to_app_error
from tourneyhub.services.tournaments.fields import _fill_fields
from tourneyhub.services.tournaments.places import _ranking
from tourneyhub.services.tournaments.shared import (
    ROUND_BY_ROUND_FORMATS,
    Clock,
    _find_match,
    _lock_tournament,
    _match_players,
    _match_slots,
    _require_open_season,
    final_round_no,
    knockout_bracket,
    knockout_phase,
)
from tourneyhub.services.tournaments.views import MatchView, _match_view, _setup_of


@dataclass(frozen=True, slots=True, kw_only=True)
class MatchResult:
    """A whole result as the organizer sends it (ADR-008, FR-050 to FR-053).

    A `walkover_winner` is a walkover, which has no games (FR-052, BR-124).
    Neither a walkover nor games is the empty result: it clears the match.
    `expected_sides` are the entries the screen saw on side 1 and side 2; a
    match whose sides are derived on read needs them (BR-094, ADR-008).
    """

    walkover_winner: Outcome | None
    games: tuple[Game, ...]
    expected_sides: tuple[UUID, UUID] | None = None

    @property
    def is_empty(self) -> bool:
        return self.walkover_winner is None and not self.games


def _match_format(phase: TournamentPhase, round_: Round, match: Match) -> MatchFormat:
    """The format a match plays: its phase's, or the final's own (BR-120).

    The final is the standard match of the bracket's last round (D4), which a
    Lord have mercy knockout draws last: until then no stored round holds it.
    """
    is_final = (
        phase.kind is PhaseKind.KNOCKOUT
        and match.kind is MatchKind.STANDARD
        and round_.round_no == final_round_no(phase)
    )
    if is_final and phase.final_match_format is not None:
        return MatchFormat(phase.final_match_format)
    return phase.match_format


def _outcome_of(
    result: MatchResult,
    *,
    league: League,
    phase: TournamentPhase,
    round_: Round,
    match: Match,
) -> Outcome:
    """The outcome a result makes, checked against the match's rules (BR-090 to BR-124)."""
    if result.walkover_winner is not None:
        return result.walkover_winner
    try:
        return match_outcome(
            result.games,
            match_format=_match_format(phase, round_, match),
            draws_allowed=league.draws_allowed and phase.kind is PhaseKind.GROUP,
            scores_required=phase.format
            in {PhaseFormat.SWISS, PhaseFormat.MONSTER_DYP},
        )
    except EngineError as err:
        raise to_app_error(err) from err


def _same_result(match: Match, result: MatchResult, outcome: Outcome) -> bool:
    stored = [(game.winner, game.score_1, game.score_2) for game in match.games]
    sent = [(game.winner, game.score_1, game.score_2) for game in result.games]
    return (
        match.outcome is outcome
        and match.is_walkover == (result.walkover_winner is not None)
        and stored == sent
    )


def set_match_result(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    match_id: UUID,
    user_id: UUID,
    result: MatchResult,
    clock: Clock,
) -> MatchView:
    """Enter, replace or clear a match's result, the target state (FR-050 to FR-053).

    The result is checked against the match's format, the draw rule and the
    scores (`engine.results`). Entering it sets the result time, frees the
    match's field and fills the free fields (FR-094, BR-130, BR-131); a waiting
    match never takes a field once it has a result. A result equal to the
    stored one changes nothing, the time included, so a repeat is harmless.

    The empty result clears it: the match waits again like any other, not
    put back on its old field (BR-134), and a finished tournament is back in
    progress (BR-095). The free fields are then filled as after any result, so
    the first match that can be played takes one (BR-130), the cleared match
    included. Clearing a match without a result changes nothing.

    A closed season is 409 `season_closed` (BR-011); an unknown match, or one
    of another tournament, 404 `match_not_found`; a match whose sides are not
    both known, or that has a bye, 422 `match_sides_unknown` (BR-091).

    The sides of a knockout match after the first round are derived from the
    winners on read (D4), so they can change between the screen and the
    write. Such a result names the entries the screen saw: others are 409
    `match_sides_changed` (detail `entry_ids`, the current ones), none 422
    `expected_sides_required` (when both sides are known). A match with stored sides never changes them,
    so the expectation is optional there; if it is sent for two entries it
    is checked the same way (ADR-008).

    The knockout (D4): a group-phase result is locked once the knockout is
    drawn, 422 `group_phase_locked` (BR-053, BR-065, detail `phase_id`, the
    knockout's); a knockout result is locked while a later match it feeds has
    a result, 422 `result_locked` (BR-094, detail `match_ids`). A repeat of
    the stored result is never refused. A new winner changes the later sides
    on the next read; a match on a field whose side is no longer known leaves
    it (BR-130). The result that completes the knockout, the final's or the
    third-place match's, finishes the tournament in the same transaction
    (FR-037). In a Swiss, every round but the newest is locked (BR-065):
    422 `round_locked` with the newest `round_no`.
    """
    league, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    _require_open_season(league, tournament)
    phase, round_, match = _find_match(tournament, match_id)
    _require_expected_sides(tournament, match, result.expected_sides)
    if _match_players(tournament)[match.id] is None or any(
        side.is_bye for side in match.sides
    ):
        raise RuleViolationError(ErrorCode.MATCH_SIDES_UNKNOWN)
    now = clock()
    if result.is_empty:
        if match.outcome is not None:
            _require_unlocked(tournament, phase, round_, match)
        _clear_result(tournament, match, now)
    else:
        outcome = _outcome_of(
            result, league=league, phase=phase, round_=round_, match=match
        )
        if not _same_result(match, result, outcome):
            _require_unlocked(tournament, phase, round_, match)
            _write_result(session, tournament, match, result, outcome, now)
            _finish_with_knockout(tournament, now)
    session.flush()
    ranking = _ranking(session, league=league, tournament=tournament)
    members = {
        entry.id: entry.player_ids for entry in _setup_of(tournament, ranking).entries
    }
    knockout = knockout_bracket(tournament)
    return _match_view(
        match, members, None if knockout is None else knockout.played.get(match.id)
    )


def _require_expected_sides(
    tournament: Tournament, match: Match, expected: tuple[UUID, UUID] | None
) -> None:
    """Check the sides the screen saw against the match's now (ADR-008, BR-094).

    Derived sides (a knockout match after round 1, the third-place match) need
    the expectation: none is 422 `expected_sides_required` (unless a side is
    still to come, which `match_sides_unknown` refuses), a different pair, or
    a side still to come, 409 `match_sides_changed`. Stored sides need none;
    a sent pair of entries is compared with them.
    """
    if match.sides:
        stored = tuple(
            side.entry_id for side in sorted(match.sides, key=lambda s: s.side)
        )
        if expected is not None and None not in stored and stored != expected:
            raise ConflictError(
                ErrorCode.MATCH_SIDES_CHANGED, entry_ids=[str(i) for i in stored]
            )
        return
    knockout = knockout_bracket(tournament)
    derived = None if knockout is None else knockout.played.get(match.id)
    if derived is None:
        return
    current = (derived.side_1.entry_id, derived.side_2.entry_id)
    if expected is None:
        if None not in current:
            raise RuleViolationError(ErrorCode.EXPECTED_SIDES_REQUIRED)
        return  # a side still to come: 422 `match_sides_unknown` follows (BR-091)
    if current != expected:
        raise ConflictError(
            ErrorCode.MATCH_SIDES_CHANGED,
            entry_ids=[None if i is None else str(i) for i in current],
        )


def _require_unlocked(
    tournament: Tournament, phase: TournamentPhase, round_: Round, match: Match
) -> None:
    """Refuse a change to a locked result (BR-053, BR-065, BR-094): 422.

    Once the knockout is drawn, every group-phase result is locked,
    `group_phase_locked`. Before that, a Swiss locks every round but the
    newest, `round_locked` with the newest `round_no` (BR-065); deleting the
    newest round unlocks the one before (BR-066), since the newest round is
    found on every write. A result of a fixed bracket is locked while a later
    match it feeds has a result, `result_locked` with those `match_ids`
    (BR-094).
    """
    drawn = knockout_phase(tournament)
    if drawn is None:
        newest = phase.rounds[-1]
        if phase.format in ROUND_BY_ROUND_FORMATS and round_ is not newest:
            raise RuleViolationError(ErrorCode.ROUND_LOCKED, round_no=newest.round_no)
        return
    if phase.kind is PhaseKind.GROUP:
        raise RuleViolationError(ErrorCode.GROUP_PHASE_LOCKED, phase_id=str(drawn.id))
    knockout = knockout_bracket(tournament)
    if knockout is None:
        return  # Lord have mercy has no fixed bracket; its round lock is BR-146
    later = locked_by(knockout.bracket, knockout.keys[match.id], knockout.outcomes)
    if later:
        raise RuleViolationError(
            ErrorCode.RESULT_LOCKED,
            match_ids=[str(knockout.rows[key].id) for key in later],
        )


def _finish_with_knockout(tournament: Tournament, now: datetime) -> None:
    """Finish a tournament whose knockout has every result (FR-037)."""
    knockout = knockout_bracket(tournament)
    if (
        knockout is not None
        and tournament.state is TournamentState.IN_PROGRESS
        and is_complete(knockout.played.values())
    ):
        tournament.state = TournamentState.FINISHED
        tournament.updated_at = now


def _clear_result(tournament: Tournament, match: Match, now: datetime) -> None:
    if match.outcome is None:
        return
    match.games.clear()
    match.outcome = None
    match.is_walkover = False
    match.result_entered_at = None
    if tournament.state is TournamentState.FINISHED:
        tournament.state = TournamentState.IN_PROGRESS
        tournament.updated_at = now
    # The match waits in schedule order like any other (BR-134); a free field
    # takes the first match that can be played (BR-130), which can be this one.
    _fill_fields(tournament, _match_slots(tournament), now)


def _write_result(
    session: Session,
    tournament: Tournament,
    match: Match,
    result: MatchResult,
    outcome: Outcome,
    now: datetime,
) -> None:
    match.games.clear()
    session.flush()  # the old games go before new ones take their numbers
    match.games.extend(
        MatchGame(
            game_no=game_no,
            winner=game.winner,
            score_1=game.score_1,
            score_2=game.score_2,
            created_at=now,
        )
        for game_no, game in enumerate(result.games, start=1)
    )
    match.outcome = outcome
    match.is_walkover = result.walkover_winner is not None
    match.result_entered_at = now
    match.requeued_at = None
    for field in tournament.fields:
        if field.match_id == match.id:
            field.match_id = None
            field.updated_at = now
    _fill_fields(tournament, _match_slots(tournament), now)
