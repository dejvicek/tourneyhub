"""Monster DYP: the top players of the group phase (FR-041, BR-061)."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from tourneyhub.engine.tournaments import EntryStage, TournamentType
from tourneyhub.errors import ConflictError, ErrorCode, RuleViolationError
from tourneyhub.services.tournaments.entries import _require_type
from tourneyhub.services.tournaments.places import _ranking
from tourneyhub.services.tournaments.shared import _lock_setup
from tourneyhub.services.tournaments.views import TournamentSetup, _setup_of

_PLAYERS_PER_MATCH = 4


def set_top_players(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    player_ids: Sequence[UUID],
) -> TournamentSetup:
    """Mark the top players the organizer picks, the target state (FR-041).

    Every marked player must be picked (409 `player_not_picked`). At most one
    per match of round 1, so at most the player count // 4 (422
    `too_many_top_players`, detail `max`). A player not listed loses the mark.
    The marks are filled up from the league ranking when a round is drawn
    (BR-061), not here.
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _require_type(tournament, TournamentType.MONSTER_DYP)
    picked = {row.player_id for row in tournament.players}
    if not set(player_ids) <= picked:
        missing = sorted(set(player_ids) - picked)
        raise ConflictError(ErrorCode.PLAYER_NOT_PICKED, player_id=str(missing[0]))
    maximum = len(picked) // _PLAYERS_PER_MATCH
    if len(player_ids) > maximum:
        raise RuleViolationError(ErrorCode.TOO_MANY_TOP_PLAYERS, max=maximum)
    marked = set(player_ids)
    for entry in tournament.entries:
        if entry.stage is EntryStage.MAIN:
            entry.is_top_player = any(m.player_id in marked for m in entry.members)
    session.flush()
    return _setup_of(
        tournament, _ranking(session, league=league, tournament=tournament)
    )
