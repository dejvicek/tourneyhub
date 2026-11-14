"""Late players in a running Swiss or Monster DYP (FR-047, BR-067, ADR-008)."""

from uuid import UUID

from sqlalchemy.orm import Session

from tourneyhub.db.models.matches import RoundParticipation
from tourneyhub.db.models.tournaments import TournamentPlayer
from tourneyhub.engine.tournaments import (
    Participation,
    PhaseFormat,
    TournamentState,
    TournamentType,
)
from tourneyhub.errors import (
    ConflictError,
    ErrorCode,
    RuleViolationError,
)
from tourneyhub.services.tournaments.entries import _league_players, _new_entry
from tourneyhub.services.tournaments.participants import Participant, _participants
from tourneyhub.services.tournaments.rounds import (
    _require_no_knockout,
    _require_round_by_round,
)
from tourneyhub.services.tournaments.shared import (
    Clock,
    _lock_tournament,
    _main_entries,
    _require_open_season,
)


def add_late_entry(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    player_id: UUID,
    from_round_no: int,
    clock: Clock,
) -> Participant:
    """Add a late player to a Swiss or Monster DYP between or during rounds (FR-047).

    Locks the league, then the tournament. The player comes from the league's
    list: an unknown one, or one of another league, is 404 `player_not_found`,
    a removed one 409 `player_removed`. A closed season is 409 `season_closed`,
    a tournament not in progress 409 `tournament_not_in_progress`. A group
    phase that is not a Swiss or Monster DYP is 422 `format_not_supported`;
    once the knockout is drawn, 422 `group_phase_locked` (BR-086). A type that
    takes no late player (DYP, Doubles) is 422 `late_entry_not_allowed`, a
    player who is already picked 422 `player_already_in_tournament`. The
    request carries the round the player is expected to start in, the newest
    group round's number plus one: any other is 409 `round_number_changed`
    (detail `current_round_no`), so a repeat adds nobody (ADR-008).

    The newest round need not be complete: a late player is drawn from the
    next round on (BR-067). The new entry starts on 0 points, has a
    `not_joined` participation row for every round so far, and so counts each
    missed round as a sit-out for the sit-out order only; the engine reads all
    of this from the stored facts (ADR-009). A Singles Swiss entry gets the
    seed after the highest, a Monster DYP entry none (BR-063). Deleting round
    1, or going back to setup, makes the entry an ordinary picked player again
    and seeds every main entry again by the seeding method (DATA-MODEL §4.5).
    """
    league, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    [player] = _league_players(session, league=league, player_ids=[player_id])
    if player.removed_at is not None:
        raise ConflictError(ErrorCode.PLAYER_REMOVED, player_id=str(player.id))
    _require_open_season(league, tournament)
    if tournament.state is not TournamentState.IN_PROGRESS:
        raise ConflictError(
            ErrorCode.TOURNAMENT_NOT_IN_PROGRESS, state=tournament.state
        )
    group = _require_round_by_round(tournament)
    _require_no_knockout(tournament)
    is_swiss = (
        tournament.type is TournamentType.SINGLES and group.format is PhaseFormat.SWISS
    )
    if not (is_swiss or tournament.type is TournamentType.MONSTER_DYP):
        raise RuleViolationError(ErrorCode.LATE_ENTRY_NOT_ALLOWED, type=tournament.type)
    if any(row.player_id == player.id for row in tournament.players):
        raise RuleViolationError(
            ErrorCode.PLAYER_ALREADY_IN_TOURNAMENT, player_id=str(player.id)
        )
    newest = group.rounds[-1]  # a running Swiss or Monster DYP has round 1 (FR-046)
    if from_round_no != newest.round_no + 1:
        raise ConflictError(
            ErrorCode.ROUND_NUMBER_CHANGED, current_round_no=newest.round_no
        )
    now = clock()
    seeds = [entry.seed for entry in _main_entries(tournament) if entry.seed]
    tournament.players.append(
        TournamentPlayer(
            tournament_id=tournament.id, player_id=player.id, created_at=now
        )
    )
    entry = _new_entry(tournament, [player.id], now)
    if is_swiss:
        entry.seed = max(seeds, default=0) + 1  # the seeds stay 1..n (BR-055)
    for round_ in group.rounds:
        round_.participation.append(
            RoundParticipation(
                entry_id=entry.id,
                status=Participation.NOT_JOINED,
                created_at=now,
            )
        )
    tournament.updated_at = now
    session.flush()
    return next(p for p in _participants(tournament) if p.entry_id == entry.id)
