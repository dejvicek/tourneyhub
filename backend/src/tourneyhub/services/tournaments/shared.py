"""Shared by the tournament use cases: loaders, locks, bracket and slots."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, insert, select
from sqlalchemy.orm import Session, selectinload

from tourneyhub.db.models.entries import Entry
from tourneyhub.db.models.leagues import League, Season
from tourneyhub.db.models.matches import (
    Match,
    MatchSide,
    MatchSidePlayer,
    Round,
    RoundParticipation,
)
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.fields import FieldSlot, MatchSlot
from tourneyhub.engine.ids import EntryId, FieldId, MatchId, PlayerId
from tourneyhub.engine.knockout import (
    Bracket,
    BracketMatch,
    FirstRoundMatch,
    MatchKey,
    bracket_of,
    match_key,
    play_bracket,
)
from tourneyhub.engine.leagues import SeasonState
from tourneyhub.engine.tournaments import (
    EntryStage,
    Outcome,
    PhaseFormat,
    PhaseKind,
    TournamentState,
)
from tourneyhub.errors import ConflictError, ErrorCode, NotFoundError
from tourneyhub.services.leagues import lock_league

MATCH_SIDES = 2
"""A match has two sides, side 1 and side 2 (DATA-MODEL §4.5)."""

PLAYED_GROUP_FORMATS = frozenset({PhaseFormat.ROUND_ROBIN, PhaseFormat.SWISS})
"""The group formats whose rounds the backend plays; Monster DYP comes later."""

ROUND_BY_ROUND_FORMATS = frozenset({PhaseFormat.SWISS, PhaseFormat.MONSTER_DYP})
"""Group formats drawn one round at a time, with tie-breakers of their own (FR-040,
FR-043)."""

type Clock = Callable[[], datetime]


_ROUNDS = selectinload(Tournament.phases).selectinload(TournamentPhase.rounds)
"""The rounds with what the list counts: matches, their results and byes."""

_ROUNDS_IN_FULL = _ROUNDS.options(
    selectinload(Round.participation),
    selectinload(Round.matches).options(
        selectinload(Match.games),
        selectinload(Match.sides).selectinload(MatchSide.players),
    ),
)
"""The rounds with everything the whole tournament shows."""


def _tournament_query(
    league: League, tournament_id: UUID, *, rounds: bool = False
) -> Select[Tournament]:
    """A tournament of the league with what setup reads, and the rounds (ADR-008)."""
    query = (
        select(Tournament)
        .join(Season, Tournament.season_id == Season.id)
        .where(Tournament.id == tournament_id, Season.league_id == league.id)
        .options(
            selectinload(Tournament.phases),
            selectinload(Tournament.fields),
            selectinload(Tournament.players),
            selectinload(Tournament.halves),
            selectinload(Tournament.entries).selectinload(Entry.members),
        )
        .execution_options(populate_existing=True)
    )
    return query.options(_ROUNDS_IN_FULL) if rounds else query


def _lock_tournament(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    rounds: bool = False,
) -> tuple[League, Tournament]:
    """Lock the league, then one of its tournaments (ADR-008).

    Another organizer's league is 404 `league_not_found`; a tournament of
    another league, or an unknown one, is 404 `tournament_not_found`.
    """
    league = lock_league(session, league_id=league_id, user_id=user_id)
    tournament = session.scalars(
        _tournament_query(league, tournament_id, rounds=rounds).with_for_update(
            of=Tournament
        )
    ).one_or_none()
    if tournament is None:
        raise NotFoundError(ErrorCode.TOURNAMENT_NOT_FOUND)
    return league, tournament


def _lock_setup(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> tuple[League, Tournament]:
    """Lock a tournament that must still be in setup.

    A started tournament is 409 `tournament_not_in_setup`: the screen that sent
    the request is stale, and the reload shows the tournament running (ADR-008).
    """
    league, tournament = _lock_tournament(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    if tournament.state is not TournamentState.SETUP:
        raise ConflictError(ErrorCode.TOURNAMENT_NOT_IN_SETUP, state=tournament.state)
    return league, tournament


def _current_phase(tournament: Tournament) -> TournamentPhase | None:
    """The phase being played: the last one that has rounds."""
    return next((phase for phase in reversed(tournament.phases) if phase.rounds), None)


def _played(round_: Round) -> list[Match]:
    """A round's matches, without a bye, which is not a match (BR-041)."""
    return [
        match
        for match in round_.matches
        if not any(side.is_bye for side in match.sides)
    ]


def _is_done(phase: TournamentPhase) -> bool:
    """Every match of the phase's rounds so far has a result."""
    return all(
        match.outcome is not None
        for round_ in phase.rounds
        for match in _played(round_)
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class KnockoutBracket:
    """A knockout phase with every match's sides derived (DATA-MODEL D4).

    Only the first round's sides are stored; `played` holds each match as the
    engine derives it from them and the stored winners, so a changed winner
    shows in the later matches on the next read (BR-094).
    """

    phase: TournamentPhase
    bracket: Bracket
    keys: Mapping[UUID, MatchKey]
    rows: Mapping[MatchKey, Match]
    outcomes: Mapping[MatchKey, Outcome]
    played: Mapping[UUID, BracketMatch]


def knockout_phase(tournament: Tournament) -> TournamentPhase | None:
    """The tournament's knockout, once it has its matches."""
    return next(
        (p for p in tournament.phases if p.kind is PhaseKind.KNOCKOUT and p.rounds),
        None,
    )


def knockout_bracket(tournament: Tournament) -> KnockoutBracket | None:
    """The knockout's bracket with its sides derived on read (D4); None without one."""
    phase = knockout_phase(tournament)
    if phase is None:
        return None
    keys = {
        match.id: match_key(
            round_no=round_.round_no, kind=match.kind, position=match.position
        )
        for round_ in phase.rounds
        for match in round_.matches
    }
    rows = {
        keys[match.id]: match for round_ in phase.rounds for match in round_.matches
    }

    def stored(match: Match, number: int) -> EntryId | None:
        side = next(side for side in match.sides if side.side == number)
        return None if side.entry_id is None else EntryId(side.entry_id)

    bracket = bracket_of(
        (
            FirstRoundMatch(
                position=match.position,
                side_1=stored(match, 1),
                side_2=stored(match, 2),
            )
            for match in phase.rounds[0].matches
        ),
        third_place_match=bool(phase.third_place_match),
    )
    outcomes = {
        key: row.outcome for key, row in rows.items() if row.outcome is not None
    }
    return KnockoutBracket(
        phase=phase,
        bracket=bracket,
        keys=keys,
        rows=rows,
        outcomes=outcomes,
        # A Lord have mercy knockout stores its later rounds only once drawn.
        played={
            rows[m.key].id: m for m in play_bracket(bracket, outcomes) if m.key in rows
        },
    )


def _match_players(tournament: Tournament) -> dict[UUID, frozenset[PlayerId] | None]:
    """Every match's players, or None while a side is not known yet (D4).

    Stored sides list their players (D2). A knockout match after the first
    round has no stored sides: its players are those of the entries the
    engine derives, and a side that waits for an earlier match is unknown.
    """
    knockout = knockout_bracket(tournament)
    derived = {} if knockout is None else knockout.played
    members = {
        entry.id: frozenset(PlayerId(member.player_id) for member in entry.members)
        for entry in tournament.entries
    }
    players: dict[UUID, frozenset[PlayerId] | None] = {}
    for phase in tournament.phases:
        for round_ in phase.rounds:
            for match in round_.matches:
                bracket_match = derived.get(match.id)
                if match.sides or bracket_match is None:
                    players[match.id] = _known_players(match)
                    continue
                sides = (bracket_match.side_1, bracket_match.side_2)
                players[match.id] = (
                    frozenset().union(
                        *(members[side.entry_id] for side in sides if side.entry_id)
                    )
                    if all(side.is_known for side in sides)
                    else None
                )
    return players


def _known_players(match: Match) -> frozenset[PlayerId] | None:
    """Every player of both stored sides, or None while a side is not known yet.

    A side is unknown when it is not stored, or is not a bye and has neither an
    entry nor players: a knockout side that waits for an earlier match.
    """
    if len(match.sides) < MATCH_SIDES or any(
        not side.is_bye and side.entry_id is None and not side.players
        for side in match.sides
    ):
        return None
    return frozenset(
        PlayerId(row.player_id) for side in match.sides for row in side.players
    )


def _match_slots(tournament: Tournament) -> list[MatchSlot]:
    """Every stored match as the field queue sees it (BR-130).

    A knockout match takes a field once the engine derives both its sides (D4).
    """
    players = _match_players(tournament)
    return [
        MatchSlot(
            match_id=MatchId(match.id),
            phase_position=phase.position,
            round_no=round_.round_no,
            kind=match.kind,
            position=match.position,
            player_ids=players[match.id],
            has_bye=any(side.is_bye for side in match.sides),
            has_result=match.outcome is not None,
            requeued_at=match.requeued_at,
        )
        for phase in tournament.phases
        for round_ in phase.rounds
        for match in round_.matches
    ]


@dataclass(frozen=True, slots=True, kw_only=True)
class _ScheduleRows:
    """The rows of drawn rounds, one list per table, in insert order (D2, D5)."""

    rounds: list[dict[str, object]]
    matches: list[dict[str, object]]
    sides: list[dict[str, object]]
    side_players: list[dict[str, object]]
    participation: list[dict[str, object]]
    slots: list[MatchSlot]


def _insert_schedule(session: Session, rows: _ScheduleRows) -> None:
    """Write the schedule's rows in bulk, parents first.

    A 64-entry double round robin has 4,032 matches and some 20,000 to 30,000
    other rows; one ORM object per row would be far too slow.
    """
    for model, table_rows in (
        (Round, rows.rounds),
        (Match, rows.matches),
        (MatchSide, rows.sides),
        (MatchSidePlayer, rows.side_players),
        (RoundParticipation, rows.participation),
    ):
        session.execute(insert(model), table_rows)


def _field_slots(tournament: Tournament) -> list[FieldSlot]:
    return [
        FieldSlot(
            field_id=FieldId(field.id),
            number=field.number,
            match_id=None if field.match_id is None else MatchId(field.match_id),
        )
        for field in tournament.fields
    ]


def _main_entries(tournament: Tournament) -> list[Entry]:
    return [entry for entry in tournament.entries if entry.stage is EntryStage.MAIN]


def _require_open_season(league: League, tournament: Tournament) -> None:
    """Refuse a change in a closed season (BR-011): 409 `season_closed`."""
    season = next(s for s in league.seasons if s.id == tournament.season_id)
    if season.state is SeasonState.CLOSED:
        raise ConflictError(ErrorCode.SEASON_CLOSED)


def _find_match(
    tournament: Tournament, match_id: UUID
) -> tuple[TournamentPhase, Round, Match]:
    """A match of the tournament with its phase and round, else 404 (ADR-008)."""
    for phase in tournament.phases:
        for round_ in phase.rounds:
            for match in round_.matches:
                if match.id == match_id:
                    return phase, round_, match
    raise NotFoundError(ErrorCode.MATCH_NOT_FOUND)


def _group_phase(tournament: Tournament) -> TournamentPhase | None:
    return next((p for p in tournament.phases if p.kind is PhaseKind.GROUP), None)


def _load_tournament(
    session: Session,
    *,
    league: League,
    tournament_id: UUID,
    past_setup: bool = False,
) -> Tournament:
    """A tournament of the league with its rounds, read without a lock.

    With `past_setup`, one in setup is not found (FR-070).
    """
    query = _tournament_query(league, tournament_id, rounds=True)
    if past_setup:
        query = query.where(Tournament.state != TournamentState.SETUP)
    tournament = session.scalars(query).one_or_none()
    if tournament is None:
        raise NotFoundError(ErrorCode.TOURNAMENT_NOT_FOUND)
    return tournament
