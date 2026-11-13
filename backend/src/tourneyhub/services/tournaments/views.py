"""The read side: the setup, the lists and the whole-tournament view."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tourneyhub.db.models.entries import Entry
from tourneyhub.db.models.leagues import League
from tourneyhub.db.models.matches import Match, MatchSide, Round
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.dyp import DypHalf
from tourneyhub.engine.fields import waiting_order
from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.knockout import BracketMatch
from tourneyhub.engine.ranking import RankedPlayer
from tourneyhub.engine.tournaments import (
    EntryKind,
    EntryStage,
    GroupPhase,
    HalvesMethod,
    KnockoutMatchFormat,
    MatchFormat,
    MatchKind,
    MonsterKnockoutMode,
    Outcome,
    Participation,
    PhaseFormat,
    PhaseKind,
    SeedingMethod,
    Tiebreaker,
    TournamentState,
    TournamentType,
)
from tourneyhub.errors import ErrorCode, NotFoundError
from tourneyhub.services.leagues import get_league
from tourneyhub.services.tournaments.places import _ranking
from tourneyhub.services.tournaments.shared import (
    _ROUNDS,
    _current_phase,
    _field_slots,
    _is_done,
    _match_slots,
    _played,
    _tournament_query,
    knockout_bracket,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class TournamentFormat:
    """Everything the format step sets (FR-030, FR-031, FR-039, BR-120).

    A value that does not apply is None: the group phase's settings without a
    group phase, the knockout's with one. A knockout after a group phase is
    created when it starts (FR-045), with the format of that request.
    """

    name: str
    date: date
    type: TournamentType
    group_phase: GroupPhase
    round_robin_legs: int | None
    sit_out_points: int | None
    group_match_format: MatchFormat | None
    knockout_match_format: KnockoutMatchFormat | None
    final_match_format: KnockoutMatchFormat | None
    third_place_match: bool | None
    goals_per_game: int
    field_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class RankingRow:
    """A player's place in the league ranking used by this tournament (BR-020)."""

    rank: int
    player_id: UUID
    points: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SetupEntry:
    """An entry as setup shows it; a pair lists its better-ranked player first."""

    id: UUID
    stage: EntryStage
    kind: EntryKind
    seed: int | None
    player_ids: tuple[UUID, ...]
    is_disabled: bool
    is_top_player: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SetupHalf:
    player_id: UUID
    half: DypHalf


@dataclass(frozen=True, slots=True, kw_only=True)
class TournamentSetup:
    """What the setup screens read: the format, the picks and the draws."""

    tournament_id: UUID
    state: TournamentState
    format: TournamentFormat
    seeding_method: SeedingMethod
    draw_counter: int
    player_ids: tuple[UUID, ...]
    halves_method: HalvesMethod
    halves: tuple[SetupHalf, ...]
    top_player_ids: tuple[UUID, ...]
    entries: tuple[SetupEntry, ...]
    ranking: tuple[RankingRow, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class PhaseSummary:
    id: UUID
    position: int
    kind: PhaseKind
    format: PhaseFormat


@dataclass(frozen=True, slots=True, kw_only=True)
class TournamentProgress:
    """How far a running tournament is (screen 1).

    `round_no` is the first group round with a match still to play, or the last
    one; byes are not matches (BR-041).
    """

    round_no: int
    round_count: int
    matches_played: int
    match_count: int
    in_knockout: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class TournamentSummary:
    """A tournament in its season's list (screen 1).

    The progress and the current phase come from the rounds; a tournament has
    none until it is generated. The winner comes with the places (P10).
    """

    id: UUID
    season_id: UUID
    name: str
    date: date
    type: TournamentType
    state: TournamentState
    phases: tuple[PhaseSummary, ...]
    current_phase_id: UUID | None
    current_phase_done: bool
    player_count: int
    progress: TournamentProgress | None
    winner_player_ids: tuple[UUID, ...] | None


def _format_of(tournament: Tournament) -> TournamentFormat:
    group = next((p for p in tournament.phases if p.kind is PhaseKind.GROUP), None)
    knockout = next(
        (
            p
            for p in tournament.phases
            if p.kind is PhaseKind.KNOCKOUT and group is None
        ),
        None,
    )
    return TournamentFormat(
        name=tournament.name,
        date=tournament.date,
        type=tournament.type,
        group_phase=GroupPhase.NONE if group is None else GroupPhase(group.format),
        round_robin_legs=None if group is None else group.round_robin_legs,
        sit_out_points=None if group is None else group.sit_out_points,
        group_match_format=None if group is None else group.match_format,
        knockout_match_format=(
            None if knockout is None else KnockoutMatchFormat(knockout.match_format)
        ),
        final_match_format=None if knockout is None else knockout.final_match_format,
        third_place_match=None if knockout is None else knockout.third_place_match,
        goals_per_game=tournament.goals_per_game,
        field_count=len(tournament.fields),
    )


def _setup_of(
    tournament: Tournament, ranking: Sequence[RankedPlayer]
) -> TournamentSetup:
    position = {ranked.player_id: ranked.position for ranked in ranking}
    halves = {row.player_id: row.half for row in tournament.halves}

    def ranked(player_ids: Iterable[UUID]) -> tuple[UUID, ...]:
        unranked = len(position) + 1
        return tuple(
            sorted(player_ids, key=lambda p: (position.get(PlayerId(p), unranked), p))
        )

    def members(entry: Entry) -> tuple[UUID, ...]:
        ordered = ranked(member.player_id for member in entry.members)
        # A DYP pair names its top-half player first (BR-033).
        return tuple(sorted(ordered, key=lambda p: halves.get(p) is not DypHalf.TOP))

    entries = sorted(
        tournament.entries,
        key=lambda e: (e.stage is not EntryStage.MAIN, e.seed is None, e.seed or 0),
    )
    return TournamentSetup(
        tournament_id=tournament.id,
        state=tournament.state,
        format=_format_of(tournament),
        seeding_method=tournament.seeding_method,
        draw_counter=tournament.draw_counter,
        player_ids=ranked(row.player_id for row in tournament.players),
        halves_method=tournament.halves_method,
        halves=tuple(
            SetupHalf(player_id=player_id, half=halves[player_id])
            for player_id in ranked(halves)
        ),
        top_player_ids=ranked(
            member.player_id
            for entry in tournament.entries
            if entry.is_top_player
            for member in entry.members
        ),
        entries=tuple(
            SetupEntry(
                id=entry.id,
                stage=entry.stage,
                kind=entry.kind,
                seed=entry.seed,
                player_ids=members(entry),
                is_disabled=entry.is_disabled,
                is_top_player=entry.is_top_player,
            )
            for entry in entries
        ),
        ranking=tuple(
            RankingRow(
                rank=ranked.position,
                player_id=ranked.player_id,
                points=ranked.season_points,
            )
            for ranked in ranking
        ),
    )


def read_tournament_setup(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> TournamentSetup:
    """Return a tournament's setup, without a lock (FR-030 to FR-034)."""
    league = get_league(session, league_id=league_id, user_id=user_id)
    tournament = session.scalars(_tournament_query(league, tournament_id)).one_or_none()
    if tournament is None:
        raise NotFoundError(ErrorCode.TOURNAMENT_NOT_FOUND)
    return _setup_of(
        tournament, _ranking(session, league=league, tournament=tournament)
    )


def list_tournaments(
    session: Session, *, league_id: UUID, season_id: UUID, user_id: UUID
) -> list[TournamentSummary]:
    """Return a season's tournaments, newest date first (FR-022, screen 1).

    A closed season's tournaments are listed too. `player_count` counts the
    picked players in setup and the players of the entries afterwards.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    return list_season_tournaments(session, league=league, season_id=season_id)


def list_season_tournaments(
    session: Session, *, league: League, season_id: UUID, past_setup: bool = False
) -> list[TournamentSummary]:
    """Return the tournaments of one of the league's seasons, newest date first.

    `past_setup` leaves out the tournaments in setup, which only the organizer
    sees (FR-070). Another league's season is 404 `season_not_found`.
    """
    if all(season.id != season_id for season in league.seasons):
        raise NotFoundError(ErrorCode.SEASON_NOT_FOUND)
    query = select(Tournament).where(Tournament.season_id == season_id)
    if past_setup:
        query = query.where(Tournament.state != TournamentState.SETUP)
    tournaments = session.scalars(
        query.options(
            selectinload(Tournament.phases),
            _ROUNDS.selectinload(Round.matches).selectinload(Match.sides),
            selectinload(Tournament.players),
            selectinload(Tournament.entries).selectinload(Entry.members),
        ).order_by(Tournament.date.desc(), Tournament.created_at.desc(), Tournament.id)
    ).all()
    return [_summary_of(tournament) for tournament in tournaments]


def _summary_of(tournament: Tournament) -> TournamentSummary:
    current = _current_phase(tournament)
    if tournament.state is TournamentState.SETUP:
        player_count = len(tournament.players)
    else:
        player_count = sum(
            len(entry.members)
            for entry in tournament.entries
            if entry.stage is EntryStage.MAIN
        )
    return TournamentSummary(
        id=tournament.id,
        season_id=tournament.season_id,
        name=tournament.name,
        date=tournament.date,
        type=tournament.type,
        state=tournament.state,
        phases=tuple(
            PhaseSummary(
                id=phase.id,
                position=phase.position,
                kind=phase.kind,
                format=phase.format,
            )
            for phase in tournament.phases
        ),
        current_phase_id=None if current is None else current.id,
        current_phase_done=current is not None and _is_done(current),
        player_count=player_count,
        progress=_progress_of(tournament),
        winner_player_ids=None,
    )


def _progress_of(tournament: Tournament) -> TournamentProgress | None:
    """How far a running tournament is; None in setup and once finished."""
    if tournament.state is not TournamentState.IN_PROGRESS:
        return None
    group = next((p for p in tournament.phases if p.kind is PhaseKind.GROUP), None)
    group_rounds = [] if group is None else group.rounds
    matches = [
        match
        for phase in tournament.phases
        for round_ in phase.rounds
        for match in _played(round_)
    ]
    current = next(
        (r for r in group_rounds if any(m.outcome is None for m in _played(r))),
        group_rounds[-1] if group_rounds else None,
    )
    return TournamentProgress(
        round_no=1 if current is None else current.round_no,
        round_count=len(group_rounds),
        matches_played=sum(match.outcome is not None for match in matches),
        match_count=len(matches),
        in_knockout=any(
            phase.rounds
            for phase in tournament.phases
            if phase.kind is PhaseKind.KNOCKOUT
        ),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class PhaseView:
    """A phase with its settings; those that do not apply are None (FR-031)."""

    id: UUID
    position: int
    kind: PhaseKind
    format: PhaseFormat
    round_robin_legs: int | None
    sit_out_points: int | None
    tiebreakers: tuple[Tiebreaker, ...] | None
    qualifiers: int | None
    third_place_match: bool | None
    monster_knockout_mode: MonsterKnockoutMode | None
    match_format: MatchFormat
    final_match_format: KnockoutMatchFormat | None


@dataclass(frozen=True, slots=True, kw_only=True)
class GameView:
    game_no: int
    winner: Outcome
    score_1: int | None
    score_2: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SideView:
    """A side: its entry, if any, and its players in the entry's order (D2)."""

    entry_id: UUID | None
    player_ids: tuple[UUID, ...]
    is_bye: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class MatchView:
    id: UUID
    round_id: UUID
    position: int
    kind: MatchKind
    sides: tuple[SideView, SideView]
    outcome: Outcome | None
    is_walkover: bool
    games: tuple[GameView, ...]
    result_entered_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class RoundView:
    """A round with its matches and the entries that sit it out (BR-051)."""

    id: UUID
    phase_id: UUID
    round_no: int
    matches: tuple[MatchView, ...]
    sitting_out: tuple[UUID, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class DrawnMatchView(MatchView):
    """A match of a Swiss round just drawn, with what a lot decided (ADR-009).

    `is_repeat`: the two have met before, as no draw without a repeat existed
    (BR-057). `is_decided_by_lot`: a lot placed either entry in the standings
    the pair was drawn from (BR-074).
    """

    is_repeat: bool
    is_decided_by_lot: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class DrawnRoundView(RoundView):
    """A Swiss round just drawn, with what a lot decided (ADR-009).

    `is_sit_out_by_lot`: a lot picked the entry that sits out from candidates
    that share its place (BR-058, BR-074). Only the draw knows these marks;
    nothing stores them.
    """

    matches: tuple[DrawnMatchView, ...]
    is_sit_out_by_lot: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class FieldView:
    id: UUID
    number: int
    match_id: UUID | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TournamentView:
    """The whole tournament: settings, entries, rounds, fields (ADR-009).

    `waiting` lists the matches waiting for a field in the order they get one,
    computed on read (FR-092). The standings and places have reads of their
    own (`read_play`, `read_places`); a tournament in setup has no rounds.
    """

    id: UUID
    season_id: UUID
    name: str
    date: date
    type: TournamentType
    state: TournamentState
    current_phase_id: UUID | None
    current_phase_done: bool
    goals_per_game: int
    phases: tuple[PhaseView, ...]
    entries: tuple[SetupEntry, ...]
    rounds: tuple[RoundView, ...]
    fields: tuple[FieldView, ...]
    waiting: tuple[UUID, ...]


def _phase_view(phase: TournamentPhase) -> PhaseView:
    return PhaseView(
        id=phase.id,
        position=phase.position,
        kind=phase.kind,
        format=phase.format,
        round_robin_legs=phase.round_robin_legs,
        sit_out_points=phase.sit_out_points,
        tiebreakers=None
        if phase.tiebreakers is None
        else tuple(Tiebreaker(t) for t in phase.tiebreakers),
        qualifiers=phase.qualifiers,
        third_place_match=phase.third_place_match,
        monster_knockout_mode=phase.monster_knockout_mode,
        match_format=phase.match_format,
        final_match_format=phase.final_match_format,
    )


def _side_view(side: MatchSide, members: Mapping[UUID, tuple[UUID, ...]]) -> SideView:
    # An entry's side has its members (D2), shown in the entry's order.
    players = (
        tuple(sorted(row.player_id for row in side.players))
        if side.entry_id is None
        else members[side.entry_id]
    )
    return SideView(entry_id=side.entry_id, player_ids=players, is_bye=side.is_bye)


def _match_view(
    match: Match,
    members: Mapping[UUID, tuple[UUID, ...]],
    derived: BracketMatch | None = None,
) -> MatchView:
    # Knockout sides after round 1 are not stored (DATA-MODEL D4): `derived`
    # gives the entries the engine derives, and a side still to come is shown
    # as an empty one.
    by_number = {side.side: _side_view(side, members) for side in match.sides}
    if derived is not None and not match.sides:
        by_number = {
            number: SideView(
                entry_id=side.entry_id,
                player_ids=members[side.entry_id],
                is_bye=False,
            )
            for number, side in ((1, derived.side_1), (2, derived.side_2))
            if side.entry_id is not None
        }
    unknown = SideView(entry_id=None, player_ids=(), is_bye=False)
    side_1, side_2 = by_number.get(1, unknown), by_number.get(2, unknown)
    return MatchView(
        id=match.id,
        round_id=match.round_id,
        position=match.position,
        kind=match.kind,
        sides=(side_1, side_2),
        outcome=match.outcome,
        is_walkover=match.is_walkover,
        games=tuple(
            GameView(
                game_no=game.game_no,
                winner=game.winner,
                score_1=game.score_1,
                score_2=game.score_2,
            )
            for game in match.games
        ),
        result_entered_at=match.result_entered_at,
    )


def _view_of(tournament: Tournament, ranking: Sequence[RankedPlayer]) -> TournamentView:
    entries = _setup_of(tournament, ranking).entries
    members = {entry.id: entry.player_ids for entry in entries}
    knockout = knockout_bracket(tournament)
    derived = {} if knockout is None else knockout.played
    current = _current_phase(tournament)
    waiting = waiting_order(
        matches=_match_slots(tournament), fields=_field_slots(tournament)
    )
    return TournamentView(
        id=tournament.id,
        season_id=tournament.season_id,
        name=tournament.name,
        date=tournament.date,
        type=tournament.type,
        state=tournament.state,
        current_phase_id=None if current is None else current.id,
        current_phase_done=current is not None and _is_done(current),
        goals_per_game=tournament.goals_per_game,
        phases=tuple(_phase_view(phase) for phase in tournament.phases),
        entries=entries,
        rounds=tuple(
            RoundView(
                id=round_.id,
                phase_id=phase.id,
                round_no=round_.round_no,
                matches=tuple(
                    _match_view(m, members, derived.get(m.id)) for m in round_.matches
                ),
                sitting_out=tuple(
                    sorted(
                        row.entry_id
                        for row in round_.participation
                        if row.status is Participation.SAT_OUT
                    )
                ),
            )
            for phase in tournament.phases
            for round_ in phase.rounds
        ),
        fields=tuple(
            FieldView(id=field.id, number=field.number, match_id=field.match_id)
            for field in tournament.fields
        ),
        waiting=tuple(slot.match_id for slot in waiting),
    )


def read_tournament(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> TournamentView:
    """Return the whole tournament, without a lock (FR-035, FR-060, FR-092)."""
    league = get_league(session, league_id=league_id, user_id=user_id)
    return view_tournament(session, league=league, tournament_id=tournament_id)


def view_tournament(
    session: Session, *, league: League, tournament_id: UUID, past_setup: bool = False
) -> TournamentView:
    """Return one of the league's tournaments whole, without a lock.

    An unknown tournament, one of another league and, with `past_setup`, one in
    setup are all 404 `tournament_not_found` (FR-070).
    """
    query = _tournament_query(league, tournament_id, rounds=True)
    if past_setup:
        query = query.where(Tournament.state != TournamentState.SETUP)
    tournament = session.scalars(query).one_or_none()
    if tournament is None:
        raise NotFoundError(ErrorCode.TOURNAMENT_NOT_FOUND)
    return _view_of(tournament, _ranking(session, league=league, tournament=tournament))
