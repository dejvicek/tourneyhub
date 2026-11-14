"""The participants of a running tournament, and disabling an entry (FR-044).

In a Swiss or Monster DYP the organizer disables an entry and enables it again
(BR-064): a disabled entry is not drawn into new rounds, its results stay, and
once enabled it is back in the draw from the next round. In a Lord have mercy
knockout a disabled player has left (BR-147). The draws read `entries.is_disabled`
and write the `disabled` participation rows themselves, so the write here changes
only the flag. Every field of the read is derived from stored facts (ADR-009).
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry
from tourneyhub.db.models.matches import Round
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.tournaments import (
    ParticipantState,
    Participation,
    PhaseKind,
    TournamentState,
)
from tourneyhub.errors import (
    ConflictError,
    ErrorCode,
    NotFoundError,
    RuleViolationError,
)
from tourneyhub.services.leagues import get_league
from tourneyhub.services.tournaments.remix import is_remix
from tourneyhub.services.tournaments.shared import (
    ROUND_BY_ROUND_FORMATS,
    Clock,
    _current_phase,
    _group_phase,
    _load_tournament,
    _lock_tournament,
    _main_entries,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Participant:
    """A main entry of a running tournament and where it stands (FR-044).

    The round fields refer to the group phase, also during a knockout.
    """

    entry_id: UUID
    state: ParticipantState
    joined_round: int | None
    disabled_since_round: int | None
    sat_out_round: int | None


def _participants(tournament: Tournament) -> list[Participant]:
    """One participant per main entry, by seed and then id (BR-064, BR-067)."""
    group = _group_phase(tournament)
    rounds: list[Round] = (
        [] if group is None else sorted(group.rounds, key=lambda r: r.round_no)
    )
    status_of = {
        (r.round_no, p.entry_id): p.status for r in rounds for p in r.participation
    }
    latest = rounds[-1].round_no if rounds else None
    participants: list[Participant] = []
    for entry in sorted(
        _main_entries(tournament),
        key=lambda e: (e.seed is None, e.seed or 0, e.id),
    ):
        history = {
            r.round_no: status_of[r.round_no, entry.id]
            for r in rounds
            if (r.round_no, entry.id) in status_of
        }
        sat_out = latest is not None and history.get(latest) is Participation.SAT_OUT
        disabled_since = None
        if entry.is_disabled:
            # The first round after the last one the entry took part in or sat out.
            disabled_since = 1 + max(
                (no for no, s in history.items() if s is not Participation.DISABLED),
                default=0,
            )
        joined = None
        if Participation.NOT_JOINED in history.values():
            joined = min(
                (no for no, s in history.items() if s is not Participation.NOT_JOINED),
                default=(latest or 0) + 1,
            )
        if entry.is_disabled:
            state = ParticipantState.DISABLED
        elif sat_out:
            state = ParticipantState.SAT_OUT
        else:
            state = ParticipantState.PLAYING
        participants.append(
            Participant(
                entry_id=entry.id,
                state=state,
                joined_round=joined,
                disabled_since_round=disabled_since,
                sat_out_round=latest if sat_out else None,
            )
        )
    return participants


def list_participants(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> list[Participant]:
    """The tournament's main entries with their state, without a lock (FR-044).

    Another league's tournament is 404 `tournament_not_found`. `state` is
    `disabled` for a disabled entry, else `sat_out` when it sat out the latest
    group round, else `playing`. `disabled_since_round` is the first round the
    entry was left out of or will be; `joined_round` is set for a late player;
    `sat_out_round` is the latest round when the entry sat it out.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    tournament = _load_tournament(session, league=league, tournament_id=tournament_id)
    return _participants(tournament)


def _require_disabling_allowed(phase: TournamentPhase | None) -> None:
    """Allow it in a Swiss or Monster DYP group phase and in Lord have mercy.

    The current phase is the latest one with rounds, so a Swiss with a knockout
    that has not started is still in its group phase (FR-044, BR-147).
    """
    group_rounds = (
        phase is not None
        and phase.kind is PhaseKind.GROUP
        and phase.format in ROUND_BY_ROUND_FORMATS
    )
    remix = phase is not None and phase.kind is PhaseKind.KNOCKOUT and is_remix(phase)
    if not (group_rounds or remix):
        raise RuleViolationError(ErrorCode.DISABLE_NOT_ALLOWED)


def set_entry_disabled(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    entry_id: UUID,
    disabled: bool,
    clock: Clock,
) -> Participant:
    """Disable or enable a main entry, the target state (FR-044, BR-064, ADR-008).

    Locks the league, then the tournament. An unknown entry, or one of another
    tournament or stage, is 404 `entry_not_found`; a tournament that is not in
    progress is 409 `tournament_not_in_progress`; a round robin, a knockout
    that is not Lord have mercy, or a Swiss or Monster DYP whose such knockout
    has started is 422 `disable_not_allowed`. A round in play is unaffected:
    only the draws that follow read the flag. A repeat changes nothing.
    """
    _, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    entry: Entry | None = next(
        (e for e in _main_entries(tournament) if e.id == entry_id), None
    )
    if entry is None:
        raise NotFoundError(ErrorCode.ENTRY_NOT_FOUND)
    if tournament.state is not TournamentState.IN_PROGRESS:
        raise ConflictError(
            ErrorCode.TOURNAMENT_NOT_IN_PROGRESS, state=tournament.state
        )
    _require_disabling_allowed(_current_phase(tournament))
    if entry.is_disabled != disabled:
        entry.is_disabled = disabled
        tournament.updated_at = clock()
        session.flush()
    return next(p for p in _participants(tournament) if p.entry_id == entry_id)
