"""Tournaments: setup, start, results, fields, standings and finishing (FR-030 to FR-094).

Every write locks the league row, then the tournament row (ADR-008), and loads
every id it is given through them. A change to the entries discards the seeding
and draws again where the inputs are complete, incrementing the draw counter
(ADR-010). Starting creates the schedule with the engine and puts the first
matches on the fields (FR-035, BR-130); going back to setup deletes it while no
match has a result (FR-036). Results and placements by hand are whole target
states (ADR-008); the standings and places are computed on read (ADR-009).
"""

import secrets
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Literal, assert_never
from uuid import UUID, uuid7

from pydantic import JsonValue
from sqlalchemy import Select, insert, select
from sqlalchemy.orm import Session, selectinload

from tourneyhub.db.models.entries import Entry, EntryMember, PlayerHalf
from tourneyhub.db.models.leagues import League, Player, Season
from tourneyhub.db.models.matches import (
    Match,
    MatchGame,
    MatchSide,
    MatchSidePlayer,
    Round,
    RoundParticipation,
)
from tourneyhub.db.models.tournaments import (
    Field,
    Tournament,
    TournamentPhase,
    TournamentPlayer,
)
from tourneyhub.engine.doubles import pair_the_rest
from tourneyhub.engine.dyp import (
    DypHalf,
    DypHalves,
    check_hand_halves,
    draw_partners,
    split_halves_by_ranking,
)
from tourneyhub.engine.errors import EngineError, NotEnoughPlayersError
from tourneyhub.engine.fields import (
    FieldSlot,
    HandPlacement,
    MatchSlot,
    fill_fields,
    next_field_number,
    place_by_hand,
    waiting_order,
)
from tourneyhub.engine.ids import EntryId, FieldId, MatchId, PlayerId
from tourneyhub.engine.knockout import (
    MAX_KNOCKOUT_ENTRIES,
    Bracket,
    BracketMatch,
    FirstRoundMatch,
    MatchKey,
    RoundName,
    bracket_of,
    draw_bracket,
    is_complete,
    knockout_results,
    locked_by,
    match_key,
    play_bracket,
    round_name,
)
from tourneyhub.engine.leagues import SeasonState
from tourneyhub.engine.lots import RNG_SEED_SIZE
from tourneyhub.engine.places import EntryPlace, PlacingEntry, place_entries
from tourneyhub.engine.ranking import PlayerRecord, RankedPlayer, rank_league
from tourneyhub.engine.results import Game, match_outcome
from tourneyhub.engine.schedule import (
    MAX_ROUND_ROBIN_ENTRIES,
    ScheduledMatch,
    ScheduledRound,
    check_entry_count,
    round_robin,
    seed_order,
)
from tourneyhub.engine.season_points import PlayerPoints, season_points
from tourneyhub.engine.season_standings import SeasonStandingRow, season_standings
from tourneyhub.engine.seeding import SeedingEntry, seed_by_lot, seed_by_ranking
from tourneyhub.engine.standings import (
    FormResult,
    PlayedMatch,
    RoundRobinTiebreaker,
    StandingRow,
    round_robin_standings,
)
from tourneyhub.engine.swiss import (
    SwissDraw,
    SwissMatch,
    SwissRound,
    SwissStanding,
    draw_first_swiss_round,
    draw_next_swiss_round,
    swiss_standings,
)
from tourneyhub.engine.tournaments import (
    DEFAULT_SIT_OUT_POINTS,
    DEFAULT_TIEBREAKERS,
    EntryKind,
    EntryStage,
    GroupPhase,
    HalvesMethod,
    KnockoutMatchFormat,
    MatchFormat,
    MatchKind,
    MatchOutcome,
    MonsterKnockoutMode,
    Outcome,
    Participation,
    PhaseFormat,
    PhaseKind,
    SeedingMethod,
    Tiebreaker,
    TournamentState,
    TournamentType,
    group_phase_format,
    is_seeded,
)
from tourneyhub.errors import (
    ConflictError,
    ErrorCode,
    NotFoundError,
    RuleViolationError,
)
from tourneyhub.services.engine_errors import to_app_error
from tourneyhub.services.leagues import active_season, get_league, lock_league

MATCH_SIDES = 2
"""A match has two sides, side 1 and side 2 (DATA-MODEL §4.5)."""

PLAYED_GROUP_FORMATS = frozenset({PhaseFormat.ROUND_ROBIN, PhaseFormat.SWISS})
"""The group formats whose rounds the backend plays; Monster DYP comes later."""

ROUND_BY_ROUND_FORMATS = frozenset({PhaseFormat.SWISS, PhaseFormat.MONSTER_DYP})
"""Group formats drawn one round at a time, with tie-breakers of their own (FR-040,
FR-043)."""

type Clock = Callable[[], datetime]


class DrawTarget(StrEnum):
    """What "draw again" draws: the pairs (DYP, Doubles) or the seeds (shuffle)."""

    PAIRS = "pairs"
    SEEDS = "seeds"


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
class FormatRequest:
    """A format as a request gives it: None takes the league's default on create.

    `goals_per_game`, `field_count` and the applicable match format copy the
    league's defaults (FR-030, DATA-MODEL §4.2); `round_robin_legs` is 1 and
    `third_place_match` false. In Swiss and Monster DYP a `sit_out_points` of
    None takes the default, 0 (FR-039); 0, 1 or 2 are stored as given (BR-075).
    A round robin has none, so a number there is refused (BR-071).
    """

    name: str
    date: date
    type: TournamentType
    group_phase: GroupPhase
    round_robin_legs: int | None = None
    sit_out_points: int | None = None
    group_match_format: MatchFormat | None = None
    knockout_match_format: KnockoutMatchFormat | None = None
    final_match_format: KnockoutMatchFormat | None = None
    third_place_match: bool | None = None
    goals_per_game: int | None = None
    field_count: int | None = None


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


# ---------------------------------------------------------------- loading


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


def _standings_by_player(
    session: Session, season: Season
) -> dict[PlayerId, SeasonStandingRow]:
    """A season's standings by player: its finished tournaments, added up (BR-112)."""
    points = finished_season_points(session, season=season)
    return {row.player_id: row for row in season_standings(points.values())}


def _previous_season(league: League, season: Season) -> Season | None:
    """The season that started before this one, the latest of them, if any."""
    earlier = [s for s in league.seasons if s.number < season.number]
    return max(earlier, key=lambda s: s.number, default=None)


def _ranking(
    session: Session, *, league: League, tournament: Tournament
) -> tuple[RankedPlayer, ...]:
    """The league ranking of the players on the list, for this tournament (BR-020).

    The final lot uses the tournament's seed (ADR-010). While the tournament is
    in setup, the season points and wins are those of the tournament's season
    and `last_season_place` is the place in the previous season's standings,
    all from finished tournaments (BR-112), as of now. Once it has started, the
    ranking only orders the names inside an entry: seeds and halves are stored,
    and the order must not shift as other tournaments finish. So a started
    tournament skips the standings, which are two reads of every finished
    tournament of two seasons on each poll of a viewer, and ranks everyone
    equal, by lot.
    """
    player_ids = session.scalars(
        select(Player.id).where(
            Player.league_id == league.id, Player.removed_at.is_(None)
        )
    ).all()
    current: dict[PlayerId, SeasonStandingRow] = {}
    last: dict[PlayerId, SeasonStandingRow] = {}
    if tournament.state is TournamentState.SETUP:
        season = _season_of(league, tournament.season_id)
        current = _standings_by_player(session, season)
        previous = _previous_season(league, season)
        if previous is not None:
            last = _standings_by_player(session, previous)
    records: list[PlayerRecord] = []
    for player_id in player_ids:
        key = PlayerId(player_id)
        now = current.get(key)
        before = last.get(key)
        records.append(
            PlayerRecord(
                player_id=key,
                season_points=0 if now is None else now.points,
                tournament_wins=0 if now is None else now.tournament_wins,
                last_season_place=None if before is None else before.place,
            )
        )
    return rank_league(records, rng_seed=tournament.rng_seed)


# ---------------------------------------------------------------- reading


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


# ---------------------------------------------------------------- format


def _resolve_format(request: FormatRequest, league: League) -> TournamentFormat:
    """Fill in what the request left out from the league's defaults (FR-030).

    BO2 needs a league that allows draws (BR-121): 422 `draws_not_allowed`.
    A round robin has no points for sitting out (BR-071): a number is 422
    `sit_out_points_not_applicable`.
    """
    default_format = league.default_match_format.value
    base = TournamentFormat(
        name=request.name,
        date=request.date,
        type=request.type,
        group_phase=request.group_phase,
        round_robin_legs=None,
        sit_out_points=None,
        group_match_format=None,
        knockout_match_format=None,
        final_match_format=None,
        third_place_match=None,
        goals_per_game=request.goals_per_game or league.default_goals_per_game,
        field_count=request.field_count or league.default_field_count,
    )
    if request.group_phase is GroupPhase.NONE:
        resolved = replace(
            base,
            knockout_match_format=request.knockout_match_format
            or KnockoutMatchFormat(default_format),
            final_match_format=request.final_match_format,
            third_place_match=bool(request.third_place_match),
        )
    else:
        group_match_format = request.group_match_format or MatchFormat(default_format)
        # BR-071: only Swiss and Monster DYP score a sit-out, so a change to a
        # round robin drops the value and a change back starts from the default.
        round_robin = request.group_phase is GroupPhase.ROUND_ROBIN
        if round_robin and request.sit_out_points is not None:
            raise RuleViolationError(ErrorCode.SIT_OUT_POINTS_NOT_APPLICABLE)
        sit_out_points = None
        if not round_robin:
            sit_out_points = (
                DEFAULT_SIT_OUT_POINTS  # FR-039
                if request.sit_out_points is None
                else request.sit_out_points  # BR-075: the organizer's pick
            )
        resolved = replace(
            base,
            round_robin_legs=(request.round_robin_legs or 1)
            if request.group_phase is GroupPhase.ROUND_ROBIN
            else None,
            sit_out_points=sit_out_points,
            group_match_format=group_match_format,
        )
    if resolved.group_match_format is MatchFormat.BO2 and not league.draws_allowed:
        raise RuleViolationError(ErrorCode.DRAWS_NOT_ALLOWED)
    return resolved


def _phase_settings(fmt: TournamentFormat) -> dict[str, object]:
    """The one phase that setup creates, as column values (FR-031, D9)."""
    group_format = group_phase_format(fmt.group_phase)
    if group_format is None:
        return {
            "kind": PhaseKind.KNOCKOUT,
            "format": PhaseFormat.SINGLE_ELIMINATION,
            "round_robin_legs": None,
            "sit_out_points": None,
            "third_place_match": fmt.third_place_match,
            "match_format": MatchFormat(fmt.knockout_match_format or MatchFormat.BO1),
            "final_match_format": fmt.final_match_format,
        }
    return {
        "kind": PhaseKind.GROUP,
        "format": group_format,
        "round_robin_legs": fmt.round_robin_legs,
        "sit_out_points": fmt.sit_out_points,
        "third_place_match": None,
        "match_format": fmt.group_match_format,
        "final_match_format": None,
    }


def _apply_phases(
    session: Session, tournament: Tournament, fmt: TournamentFormat, now: datetime
) -> bool:
    """Make the tournament's one phase match the format; True if anything changed.

    A knockout after a group phase is created when it starts (FR-045), so setup
    keeps exactly one phase at position 1. The tie-breakers of a Swiss or
    Monster DYP phase start at FR-043's default and stay only while its format
    does: a change between the two, or from another format, starts again.
    """
    settings = _phase_settings(fmt)
    phase = next(iter(tournament.phases), None)
    if phase is not None and phase.kind is not settings["kind"]:
        tournament.phases.remove(phase)
        session.flush()  # free position 1 before the new phase takes it
        phase = None
    old_format = None if phase is None else phase.format  # before it is overwritten
    if phase is None:
        phase = TournamentPhase(id=uuid7(), position=1, created_at=now)
        tournament.phases.append(phase)
    elif all(getattr(phase, column) == value for column, value in settings.items()):
        return False
    else:
        phase.updated_at = now
    for column, value in settings.items():
        setattr(phase, column, value)
    if settings["format"] not in {PhaseFormat.SWISS, PhaseFormat.MONSTER_DYP}:
        phase.tiebreakers = None
    elif old_format is not settings["format"]:
        # A new phase, or another format: Swiss and Monster DYP do not share an order.
        phase.tiebreakers = list(DEFAULT_TIEBREAKERS)
    return True


def _apply_fields(tournament: Tournament, count: int, now: datetime) -> bool:
    """Make fields 1 to `count`, keeping the ones that stay (DATA-MODEL §4.6)."""
    numbers = {field.number for field in tournament.fields}
    if numbers == set(range(1, count + 1)):
        return False
    for field in [f for f in tournament.fields if f.number > count]:
        tournament.fields.remove(field)
    for number in sorted(set(range(1, count + 1)) - numbers):
        tournament.fields.append(Field(id=uuid7(), number=number, created_at=now))
    return True


def create_tournament(
    session: Session,
    *,
    league_id: UUID,
    user_id: UUID,
    tournament_id: UUID,
    request: FormatRequest,
    clock: Clock,
) -> TournamentSetup:
    """Create a tournament in the league's active season, in setup (FR-030, ADR-008).

    The id comes from the client and is looked up before any rule is checked:
    a repeat gets its tournament back if it is in this league's active season
    and has the same type; any other tournament with the id is 409
    `tournament_id_taken`. The league lock keeps the create from racing a new
    season (ADR-008). The tournament gets a random 128-bit seed (ADR-010), its
    phase and its fields, and the league's defaults where the request left a
    value out.
    """
    league = lock_league(session, league_id=league_id, user_id=user_id)
    season = active_season(league)
    existing = session.scalars(
        select(Tournament)
        .where(Tournament.id == tournament_id)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if existing is not None:
        if existing.season_id != season.id or existing.type is not request.type:
            raise ConflictError(ErrorCode.TOURNAMENT_ID_TAKEN)
        return read_tournament_setup(
            session, league_id=league.id, tournament_id=existing.id, user_id=user_id
        )
    fmt = _resolve_format(request, league)
    now = clock()
    tournament = Tournament(
        id=tournament_id,
        season_id=season.id,
        name=fmt.name,
        date=fmt.date,
        type=fmt.type,
        state=TournamentState.SETUP,
        seeding_method=SeedingMethod.RANKING,
        halves_method=HalvesMethod.RANKING,
        rng_seed=secrets.token_bytes(RNG_SEED_SIZE),
        draw_counter=0,
        goals_per_game=fmt.goals_per_game,
        created_at=now,
        phases=[],
        fields=[],
        players=[],
        halves=[],
        entries=[],
    )
    session.add(tournament)
    _apply_phases(session, tournament, fmt, now)
    _apply_fields(tournament, fmt.field_count, now)
    session.flush()
    return _setup_of(
        tournament, _ranking(session, league=league, tournament=tournament)
    )


def set_tournament_format(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    fmt: FormatRequest,
    clock: Clock,
) -> TournamentSetup:
    """Set the whole format of a tournament in setup, the target state (FR-030).

    A repeat changes nothing (ADR-008). A new type keeps the picked players and
    makes the entries again (ADR-010): Doubles pairs and hand-set DYP halves do
    not carry over to another type.
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    resolved = _resolve_format(fmt, league)
    now = clock()
    changed = _apply_phases(session, tournament, resolved, now)
    changed = _apply_fields(tournament, resolved.field_count, now) or changed
    values = {
        "name": resolved.name,
        "date": resolved.date,
        "goals_per_game": resolved.goals_per_game,
    }
    for column, value in values.items():
        if getattr(tournament, column) != value:
            setattr(tournament, column, value)
            changed = True
    ranking = _ranking(session, league=league, tournament=tournament)
    if tournament.type is not resolved.type:
        tournament.type = resolved.type
        for half in list(tournament.halves):
            tournament.halves.remove(half)
        tournament.halves_method = HalvesMethod.RANKING
        _discard_entries(session, tournament)
        _new_draw(session, tournament, ranking, now)
        changed = True
    if changed:
        tournament.updated_at = now
    session.flush()
    return _setup_of(tournament, ranking)


# ---------------------------------------------------------------- entries


def _discard_entries(session: Session, tournament: Tournament) -> None:
    for entry in list(tournament.entries):
        tournament.entries.remove(entry)
    session.flush()  # the members' players are free before new entries take them


def _new_entry(
    tournament: Tournament, player_ids: Iterable[UUID], now: datetime
) -> None:
    entry_id = uuid7()
    members = sorted(player_ids)
    tournament.entries.append(
        Entry(
            id=entry_id,
            tournament_id=tournament.id,
            stage=EntryStage.MAIN,
            kind=EntryKind.PLAYER if len(members) == 1 else EntryKind.PAIR,
            created_at=now,
            members=[
                EntryMember(
                    entry_id=entry_id,
                    player_id=player_id,
                    tournament_id=tournament.id,
                    stage=EntryStage.MAIN,
                    created_at=now,
                )
                for player_id in members
            ],
        )
    )


def _set_entries(
    session: Session,
    tournament: Tournament,
    groups: Iterable[frozenset[UUID]],
    now: datetime,
) -> None:
    """Make the main entries exactly `groups`, keeping the entries that stay."""
    wanted = set(groups)
    kept: set[frozenset[UUID]] = set()
    for entry in list(tournament.entries):
        players = frozenset(member.player_id for member in entry.members)
        if players in wanted and entry.stage is EntryStage.MAIN:
            kept.add(players)
        else:
            tournament.entries.remove(entry)
    session.flush()  # the members' players are free before new entries take them
    for players in sorted(wanted - kept, key=sorted):
        _new_entry(tournament, players, now)
    session.flush()


def _halves_of(tournament: Tournament) -> DypHalves | None:
    """The DYP halves when every picked player has one and they are valid (BR-032)."""
    halves = {PlayerId(row.player_id): row.half for row in tournament.halves}
    if len(halves) != len(tournament.players):
        return None
    try:
        return check_hand_halves(halves)
    except EngineError:
        return None


def _set_ranking_halves(
    tournament: Tournament, ranking: Sequence[RankedPlayer], now: datetime
) -> None:
    """Split the picked players by the league ranking (BR-032), or clear the halves.

    With fewer than 4 players there are no halves yet (BR-031).
    """
    picked = {row.player_id for row in tournament.players}
    try:
        split = split_halves_by_ranking(
            (ranked for ranked in ranking if ranked.player_id in picked),
            rng_seed=tournament.rng_seed,
            draw_counter=tournament.draw_counter,
        )
    except NotEnoughPlayersError:
        target: dict[UUID, DypHalf] = {}
    else:
        target = dict.fromkeys(split.top, DypHalf.TOP)
        target |= dict.fromkeys(split.bottom, DypHalf.BOTTOM)
        if split.left_out is not None:
            target[split.left_out] = DypHalf.LEFT_OUT
    _write_halves(tournament, target, now)


def _write_halves(
    tournament: Tournament, target: Mapping[UUID, DypHalf], now: datetime
) -> None:
    """Make the halves rows exactly `target`, updating rows in place."""
    for row in list(tournament.halves):
        if row.player_id not in target:
            tournament.halves.remove(row)
        else:
            row.half = target[row.player_id]
    have = {row.player_id for row in tournament.halves}
    for player_id in sorted(set(target) - have):
        tournament.halves.append(
            PlayerHalf(
                tournament_id=tournament.id,
                player_id=player_id,
                half=target[player_id],
                created_at=now,
            )
        )


def _redraw(
    session: Session,
    tournament: Tournament,
    ranking: Sequence[RankedPlayer],
    now: datetime,
) -> None:
    """Make the entries from the picks and draw again where the inputs are complete.

    ADR-010: Singles and Monster DYP enter each picked player; Doubles keeps the
    pairs whose players are both still picked; DYP splits the halves by the
    ranking (or keeps the hand-set ones) and draws the partners once the halves
    are complete and valid. The seeds follow the seeding method; a hand order is
    discarded. Call it after incrementing the draw counter.
    """
    picked = {row.player_id for row in tournament.players}
    groups: list[frozenset[UUID]] = []
    if tournament.type is TournamentType.DOUBLES:
        groups = [
            players
            for entry in tournament.entries
            if (players := frozenset(m.player_id for m in entry.members)) <= picked
            and len(players) == 2  # noqa: PLR2004  (a pair, BR-030)
        ]
    elif tournament.type is TournamentType.DYP:
        if tournament.halves_method is HalvesMethod.RANKING:
            _set_ranking_halves(tournament, ranking, now)
        halves = _halves_of(tournament)
        if halves is not None:
            groups = [
                frozenset({pair.top, pair.bottom})
                for pair in draw_partners(
                    halves,
                    rng_seed=tournament.rng_seed,
                    draw_counter=tournament.draw_counter,
                )
            ]
    else:
        groups = [frozenset({player_id}) for player_id in picked]
    _set_entries(session, tournament, groups, now)
    _seed(tournament, ranking)


def _seed(tournament: Tournament, ranking: Sequence[RankedPlayer]) -> None:
    """Seed the main entries by the tournament's method (FR-034, BR-021, BR-022)."""
    main = [entry for entry in tournament.entries if entry.stage is EntryStage.MAIN]
    if not is_seeded(tournament.type):
        for entry in main:
            entry.seed = None
        return
    if tournament.seeding_method is SeedingMethod.RANKING:
        order = seed_by_ranking(
            (
                SeedingEntry(
                    entry_id=EntryId(entry.id),
                    player_ids=tuple(PlayerId(m.player_id) for m in entry.members),
                )
                for entry in main
            ),
            ranking,
        )
    else:
        order = seed_by_lot(
            (EntryId(entry.id) for entry in main),
            rng_seed=tournament.rng_seed,
            draw_counter=tournament.draw_counter,
        )
    seeds = {entry_id: seed for seed, entry_id in enumerate(order, start=1)}
    for entry in main:
        entry.seed = seeds[EntryId(entry.id)]


def _new_draw(
    session: Session,
    tournament: Tournament,
    ranking: Sequence[RankedPlayer],
    now: datetime,
) -> None:
    tournament.draw_counter += 1
    tournament.updated_at = now
    _redraw(session, tournament, ranking, now)


def _league_players(
    session: Session, *, league: League, player_ids: Iterable[UUID]
) -> list[Player]:
    """Load players through the league: an id of another league is 404 (ADR-008)."""
    ids = set(player_ids)
    players = list(
        session.scalars(
            select(Player).where(Player.league_id == league.id, Player.id.in_(ids))
        )
    )
    if len(players) != len(ids):
        raise NotFoundError(ErrorCode.PLAYER_NOT_FOUND)
    return players


def set_tournament_players(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    player_ids: Sequence[UUID],
    clock: Clock,
) -> TournamentSetup:
    """Set the players picked for a tournament in setup, the target state (FR-032).

    A removed player cannot be picked (BR-002): 409 `player_removed`, because only a
    screen that was not reloaded after the removal offers one (ADR-008). A changed
    pick makes the entries again and increments the draw counter (ADR-010); a
    repeat changes nothing. The minimum number of entries is checked when the
    tournament is generated (FR-032, FR-035).
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    players = _league_players(session, league=league, player_ids=player_ids)
    removed = sorted(player.id for player in players if player.removed_at is not None)
    if removed:
        raise ConflictError(ErrorCode.PLAYER_REMOVED, player_id=str(removed[0]))
    ranking = _ranking(session, league=league, tournament=tournament)
    wanted = set(player_ids)
    have = {row.player_id for row in tournament.players}
    if wanted == have:
        return _setup_of(tournament, ranking)
    now = clock()
    for half in [row for row in tournament.halves if row.player_id not in wanted]:
        tournament.halves.remove(half)
    for row in [row for row in tournament.players if row.player_id not in wanted]:
        tournament.players.remove(row)
    for player_id in sorted(wanted - have):
        tournament.players.append(
            TournamentPlayer(
                tournament_id=tournament.id, player_id=player_id, created_at=now
            )
        )
    session.flush()
    _new_draw(session, tournament, ranking, now)
    session.flush()
    return _setup_of(tournament, ranking)


def _require_type(tournament: Tournament, *types: TournamentType) -> None:
    """A write meant for another type comes from a stale screen: 409 (ADR-008)."""
    if tournament.type not in types:
        raise ConflictError(ErrorCode.TOURNAMENT_TYPE_CHANGED, type=tournament.type)


def _require_picked(tournament: Tournament, player_ids: Iterable[UUID]) -> None:
    """Every player must be picked; otherwise the screen is stale: 409 (ADR-008)."""
    picked = {row.player_id for row in tournament.players}
    missing = sorted(set(player_ids) - picked)
    if missing:
        raise ConflictError(ErrorCode.PLAYER_NOT_PICKED, player_id=str(missing[0]))


def set_doubles_pairs(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    pairs: Sequence[tuple[UUID, UUID]],
    clock: Clock,
) -> TournamentSetup:
    """Set a Doubles tournament's pairs, the target state (FR-033, BR-003, BR-030).

    Every player must be picked (409 `player_not_picked`); picked players left
    out of `pairs` have no partner yet. A change seeds again and increments the
    draw counter (ADR-010); a repeat changes nothing.
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _require_type(tournament, TournamentType.DOUBLES)
    _require_picked(tournament, (player for pair in pairs for player in pair))
    ranking = _ranking(session, league=league, tournament=tournament)
    wanted = {frozenset(pair) for pair in pairs}
    have = {
        frozenset(m.player_id for m in entry.members) for entry in tournament.entries
    }
    if wanted == have:
        return _setup_of(tournament, ranking)
    now = clock()
    _set_entries(session, tournament, wanted, now)
    _new_draw(session, tournament, ranking, now)
    session.flush()
    return _setup_of(tournament, ranking)


def set_dyp_halves(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    method: HalvesMethod,
    halves: Mapping[UUID, DypHalf],
    clock: Clock,
) -> TournamentSetup:
    """Set how a DYP tournament's halves are made, and by hand the halves (FR-033).

    `ranking` splits the picked players by the league ranking and ignores
    `halves` (BR-032). `by_hand` stores `halves` as the target state; every
    player in it must be picked (409 `player_not_picked`), and a picked player
    left out has no half yet. Once every picked player has a half and the halves
    are valid (BR-032), the partners are drawn (BR-033); until then there are no
    pairs. A change increments the draw counter (ADR-010); a repeat changes
    nothing.
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _require_type(tournament, TournamentType.DYP)
    ranking = _ranking(session, league=league, tournament=tournament)
    current = {row.player_id: row.half for row in tournament.halves}
    if method is HalvesMethod.BY_HAND:
        _require_picked(tournament, halves)
        if tournament.halves_method is method and current == dict(halves):
            return _setup_of(tournament, ranking)
    elif tournament.halves_method is method:
        return _setup_of(tournament, ranking)
    now = clock()
    tournament.halves_method = method
    if method is HalvesMethod.BY_HAND:
        _write_halves(tournament, halves, now)
    _new_draw(session, tournament, ranking, now)
    session.flush()
    return _setup_of(tournament, ranking)


def set_seeding_method(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    method: SeedingMethod,
    clock: Clock,
) -> TournamentSetup:
    """Seed by league ranking or by random shuffle, the target state (FR-034).

    Monster DYP has no seeds: 409 `tournament_type_changed`. A change seeds
    again, discarding a hand order, and increments the draw counter (ADR-010).
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _require_type(
        tournament, TournamentType.SINGLES, TournamentType.DOUBLES, TournamentType.DYP
    )
    ranking = _ranking(session, league=league, tournament=tournament)
    if tournament.seeding_method is method:
        return _setup_of(tournament, ranking)
    now = clock()
    tournament.seeding_method = method
    tournament.draw_counter += 1
    tournament.updated_at = now
    _seed(tournament, ranking)
    session.flush()
    return _setup_of(tournament, ranking)


def set_seed_order(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    entry_ids: Sequence[UUID],
    clock: Clock,
) -> TournamentSetup:
    """Reorder the seeds by hand: the full order, seed 1 first (FR-034, ADR-008).

    An order that does not list exactly the current main entries is 409
    `seed_order_changed`. It is not a draw, so the counter stays; the next
    change to the entries discards it (ADR-010).
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _require_type(
        tournament, TournamentType.SINGLES, TournamentType.DOUBLES, TournamentType.DYP
    )
    main = {e.id: e for e in tournament.entries if e.stage is EntryStage.MAIN}
    if len(entry_ids) != len(main) or set(entry_ids) != set(main):
        raise ConflictError(ErrorCode.SEED_ORDER_CHANGED)
    changed = False
    for seed, entry_id in enumerate(entry_ids, start=1):
        if main[entry_id].seed != seed:
            main[entry_id].seed = seed
            changed = True
    if changed:
        tournament.updated_at = clock()
    session.flush()
    return _setup_of(
        tournament, _ranking(session, league=league, tournament=tournament)
    )


def draw_again(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    target: DrawTarget,
    expected_draw_counter: int,
    clock: Clock,
) -> TournamentSetup:
    """Draw again: a new DYP draw, pairing the rest, or shuffling (FR-033, FR-034).

    The request carries the draw counter the screen showed; a stale one is 409
    `draw_counter_changed`, so a repeat never draws twice (ADR-008).

    - `pairs` in DYP draws the halves again when they come from the ranking, and
      the partners; hand-set halves must be complete and valid (422
      `dyp_halves_incomplete`, `dyp_halves_unequal`, `too_many_left_out`,
      `not_enough_players`).
    - `pairs` in Doubles pairs the players without a partner by lot; with fewer
      than two of them it is 422 `nothing_to_pair` and changes nothing.
    - `seeds` shuffles the seeds again; only with random seeding (409
      `seeding_method_changed`).
    """
    league, tournament = _lock_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    if tournament.draw_counter != expected_draw_counter:
        raise ConflictError(
            ErrorCode.DRAW_COUNTER_CHANGED, draw_counter=tournament.draw_counter
        )
    ranking = _ranking(session, league=league, tournament=tournament)
    now = clock()
    if target is DrawTarget.SEEDS:
        _require_type(
            tournament,
            TournamentType.SINGLES,
            TournamentType.DOUBLES,
            TournamentType.DYP,
        )
        if tournament.seeding_method is not SeedingMethod.RANDOM:
            raise ConflictError(
                ErrorCode.SEEDING_METHOD_CHANGED,
                seeding_method=tournament.seeding_method,
            )
        tournament.draw_counter += 1
        tournament.updated_at = now
        _seed(tournament, ranking)
    elif tournament.type is TournamentType.DOUBLES:
        _pair_the_rest(session, tournament, ranking, now)
    else:
        _require_type(tournament, TournamentType.DYP)
        _check_dyp_draw(tournament)
        _new_draw(session, tournament, ranking, now)
    session.flush()
    return _setup_of(tournament, ranking)


def _check_dyp_draw(tournament: Tournament) -> None:
    """Refuse a new DYP draw that cannot make pairs (BR-031, BR-032)."""
    try:
        if tournament.halves_method is HalvesMethod.RANKING:
            if len(tournament.players) < 4:  # noqa: PLR2004  (BR-031)
                raise NotEnoughPlayersError(minimum=4, given=len(tournament.players))
            return
        missing = len(tournament.players) - len(tournament.halves)
        if missing:
            raise RuleViolationError(ErrorCode.DYP_HALVES_INCOMPLETE, missing=missing)
        check_hand_halves(
            {PlayerId(row.player_id): row.half for row in tournament.halves}
        )
    except EngineError as err:
        raise to_app_error(err) from err


def _pair_the_rest(
    session: Session,
    tournament: Tournament,
    ranking: Sequence[RankedPlayer],
    now: datetime,
) -> None:
    """Pair the Doubles players without a partner by lot (FR-033).

    Fewer than two of them leave nothing to pair: 422 `nothing_to_pair`, before the
    draw counter moves, so that the seeds stay as they were.
    """
    paired = {m.player_id for entry in tournament.entries for m in entry.members}
    rest = [
        PlayerId(row.player_id)
        for row in tournament.players
        if row.player_id not in paired
    ]
    if len(rest) < 2:  # noqa: PLR2004  (a pair)
        raise RuleViolationError(ErrorCode.NOTHING_TO_PAIR, unpaired=len(rest))
    tournament.draw_counter += 1
    tournament.updated_at = now
    for top, bottom in pair_the_rest(
        rest, rng_seed=tournament.rng_seed, draw_counter=tournament.draw_counter
    ):
        _new_entry(tournament, (top, bottom), now)
    session.flush()
    _seed(tournament, ranking)


# ---------------------------------------------------------------- delete


def delete_tournament(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> None:
    """Delete a tournament and everything in it, in any state (FR-038, D6).

    A tournament of a closed season stays (BR-011): 409 `season_closed`, since
    the UI shows closed seasons read-only. A repeated delete is 404.
    """
    league, tournament = _lock_tournament(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    season = next(s for s in league.seasons if s.id == tournament.season_id)
    if season.state is SeasonState.CLOSED:
        raise ConflictError(ErrorCode.SEASON_CLOSED)
    session.delete(tournament)
    session.flush()


# ---------------------------------------------------------------- the whole tournament


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
        played={rows[m.key].id: m for m in play_bracket(bracket, outcomes)},
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


def _field_slots(tournament: Tournament) -> list[FieldSlot]:
    return [
        FieldSlot(
            field_id=FieldId(field.id),
            number=field.number,
            match_id=None if field.match_id is None else MatchId(field.match_id),
        )
        for field in tournament.fields
    ]


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


# ---------------------------------------------------------------- start


def _check_ready(tournament: Tournament, phase: TournamentPhase) -> None:
    """Refuse a start whose setup is not complete (FR-032, FR-033, BR-030 to BR-032).

    A round robin, a Swiss and a knockout without a group phase are generated
    so far; Monster DYP is 422 `format_not_supported`. Doubles needs every
    picked player in a pair (422 `players_without_partner`); DYP needs its
    halves and pairs (the 422s of a new DYP draw); every type needs FR-032's
    minimum of entries, 4 for a knockout with a third-place match (422
    `not_enough_entries`). A round robin takes at most
    `MAX_ROUND_ROBIN_ENTRIES` (422 `too_many_entries_for_round_robin`), a
    knockout `MAX_KNOCKOUT_ENTRIES` (422 `too_many_entries_for_knockout`); a
    Swiss has no maximum (FR-032).
    """
    if phase.format not in {
        PhaseFormat.ROUND_ROBIN,
        PhaseFormat.SWISS,
        PhaseFormat.SINGLE_ELIMINATION,
    }:
        raise RuleViolationError(ErrorCode.FORMAT_NOT_SUPPORTED, format=phase.format)
    if tournament.type is TournamentType.DOUBLES:
        paired = {m.player_id for entry in tournament.entries for m in entry.members}
        unpaired = sum(row.player_id not in paired for row in tournament.players)
        if unpaired:
            raise RuleViolationError(
                ErrorCode.PLAYERS_WITHOUT_PARTNER, unpaired=unpaired
            )
    elif tournament.type is TournamentType.DYP:
        _check_dyp_draw(tournament)
    given = sum(e.stage is EntryStage.MAIN for e in tournament.entries)
    try:
        check_entry_count(
            tournament_type=tournament.type,
            third_place_match=bool(phase.third_place_match),
            given=given,
        )
    except EngineError as err:
        raise to_app_error(err) from err
    if phase.kind is PhaseKind.KNOCKOUT:
        if given > MAX_KNOCKOUT_ENTRIES:
            raise RuleViolationError(
                ErrorCode.TOO_MANY_ENTRIES_FOR_KNOCKOUT, limit=MAX_KNOCKOUT_ENTRIES
            )
    elif phase.format is PhaseFormat.ROUND_ROBIN and given > MAX_ROUND_ROBIN_ENTRIES:
        raise RuleViolationError(
            ErrorCode.TOO_MANY_ENTRIES_FOR_ROUND_ROBIN, limit=MAX_ROUND_ROBIN_ENTRIES
        )


def _main_entries(tournament: Tournament) -> list[Entry]:
    return [entry for entry in tournament.entries if entry.stage is EntryStage.MAIN]


def _round_robin_of(
    main: Sequence[Entry], phase: TournamentPhase
) -> tuple[ScheduledRound, ...]:
    """The round robin of the main entries by seed (BR-050 to BR-052).

    Start writes it and the preview shows it, so both come from this one call.
    """
    return round_robin(
        seed_order((EntryId(entry.id), entry.seed) for entry in main),
        legs=phase.round_robin_legs or 1,  # the CHECK sets it for a round robin
    )


def _swiss_round_of(draw: SwissDraw) -> ScheduledRound:
    """A drawn Swiss round as the rows of a schedule take it (BR-055 to BR-058)."""
    return ScheduledRound(
        round_no=draw.round_no,
        matches=tuple(
            ScheduledMatch(side_1=pair.side_1, side_2=pair.side_2)
            for pair in draw.pairs
        ),
        sitting_out=draw.sitting_out,
    )


def _group_schedule(
    main: Sequence[Entry], phase: TournamentPhase
) -> tuple[ScheduledRound, ...]:
    """What the start writes for a group phase, and the preview shows.

    A round robin's every round (BR-050 to BR-052); a Swiss's round 1 from
    the seeds, the lowest seed sitting out with an odd number (BR-055,
    BR-058). Fewer than 2 entries is 422 `not_enough_entries`.
    """
    if phase.format is not PhaseFormat.SWISS:
        return _round_robin_of(main, phase)
    try:
        draw = draw_first_swiss_round(
            seed_order((EntryId(entry.id), entry.seed) for entry in main)
        )
    except EngineError as err:
        raise to_app_error(err) from err
    return (_swiss_round_of(draw),)


def _bracket_from_seeds(main: Sequence[Entry], phase: TournamentPhase) -> Bracket:
    """The bracket of a knockout without a group phase, by setup seed (BR-040 to BR-044).

    The setup seeds are the knockout's seeds (FR-034): the byes go to the top
    seeds and seeds 1 and 2 can meet only in the final. Start writes it and
    the preview shows it, so both come from this one call.
    """
    return draw_bracket(
        seed_order((EntryId(entry.id), entry.seed) for entry in main),
        third_place_match=bool(phase.third_place_match),
    )


def _bracket_rounds(
    bracket: Bracket, members: Mapping[UUID, Sequence[EntryMember]], now: datetime
) -> list[Round]:
    """Every round of the bracket; only the first round stores its sides (D4)."""
    rounds = [
        Round(
            id=uuid7(), round_no=round_no, created_at=now, matches=[], participation=[]
        )
        for round_no in range(1, bracket.round_count + 1)
    ]
    first = {match.position: match for match in bracket.first_round}
    for key in bracket.keys:
        sides: list[MatchSide] = []
        if key.round_no == 1:
            stored = first[key.position]
            sides = [
                MatchSide(
                    side=number,
                    entry_id=entry_id,
                    is_bye=entry_id is None,
                    created_at=now,
                    players=[
                        MatchSidePlayer(
                            side=number, player_id=member.player_id, created_at=now
                        )
                        for member in ([] if entry_id is None else members[entry_id])
                    ],
                )
                for number, entry_id in ((1, stored.side_1), (2, stored.side_2))
            ]
        rounds[key.round_no - 1].matches.append(
            Match(
                id=uuid7(),
                position=key.position,
                kind=key.kind,
                outcome=None,
                is_walkover=False,
                result_entered_at=None,
                requeued_at=None,
                created_at=now,
                sides=sides,
                games=[],
            )
        )
    return rounds


@dataclass(frozen=True, slots=True, kw_only=True)
class _ScheduleRows:
    """The rows of a round robin, one list per table, in insert order (D2, D5)."""

    rounds: list[dict[str, object]]
    matches: list[dict[str, object]]
    sides: list[dict[str, object]]
    side_players: list[dict[str, object]]
    participation: list[dict[str, object]]
    slots: list[MatchSlot]


def _schedule_rows(
    phase: TournamentPhase,
    schedule: Sequence[ScheduledRound],
    members: Mapping[UUID, Sequence[UUID]],
    now: datetime,
    *,
    disabled: Collection[UUID] = frozenset(),
) -> _ScheduleRows:
    """The rounds of the schedule with their matches, sides and participation.

    Every main entry in `members` gets a participation row in every round
    (D5): `sat_out` for the one sitting out, `disabled` for a disabled entry,
    which is not drawn (BR-064), and `played` for the others. Every stored
    side lists its players (D2). The slots are the matches as the field queue
    sees them, so no row needs loading to fill the fields.
    """
    rows = _ScheduleRows(
        rounds=[], matches=[], sides=[], side_players=[], participation=[], slots=[]
    )
    for scheduled_round in schedule:
        round_id = uuid7()
        rows.rounds.append(
            {
                "id": round_id,
                "phase_id": phase.id,
                "round_no": scheduled_round.round_no,
                "created_at": now,
            }
        )
        for position, scheduled in enumerate(scheduled_round.matches, start=1):
            match_id = uuid7()
            rows.matches.append(
                {
                    "id": match_id,
                    "round_id": round_id,
                    "position": position,
                    "kind": MatchKind.STANDARD,
                    "outcome": None,
                    "is_walkover": False,
                    "result_entered_at": None,
                    "requeued_at": None,
                    "created_at": now,
                }
            )
            players: set[PlayerId] = set()
            for side, entry_id in ((1, scheduled.side_1), (2, scheduled.side_2)):
                rows.sides.append(
                    {
                        "match_id": match_id,
                        "side": side,
                        "entry_id": entry_id,
                        "is_bye": False,
                        "created_at": now,
                    }
                )
                for player_id in members[entry_id]:
                    rows.side_players.append(
                        {
                            "match_id": match_id,
                            "side": side,
                            "player_id": player_id,
                            "created_at": now,
                        }
                    )
                    players.add(PlayerId(player_id))
            rows.slots.append(
                MatchSlot(
                    match_id=MatchId(match_id),
                    phase_position=phase.position,
                    round_no=scheduled_round.round_no,
                    kind=MatchKind.STANDARD,
                    position=position,
                    player_ids=frozenset(players),
                    has_bye=False,
                    has_result=False,
                    requeued_at=None,
                )
            )
        rows.participation.extend(
            {
                "round_id": round_id,
                "entry_id": entry_id,
                "status": Participation.SAT_OUT
                if entry_id == scheduled_round.sitting_out
                else Participation.DISABLED
                if entry_id in disabled
                else Participation.PLAYED,
                "created_at": now,
            }
            for entry_id in sorted(members)
        )
    return rows


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


def _fill_fields(
    tournament: Tournament, slots: Sequence[MatchSlot], now: datetime
) -> None:
    """Put waiting matches on the free fields (BR-130, BR-131, DATA-MODEL §4.6).

    A requeued match that takes a field is no longer requeued (BR-132).
    """
    placements = fill_fields(matches=slots, fields=_field_slots(tournament))
    fields = {field.id: field for field in tournament.fields}
    requeued = {slot.match_id for slot in slots if slot.requeued_at is not None}
    for placement in placements:
        field = fields[placement.field_id]
        field.match_id = placement.match_id
        field.updated_at = now
        if placement.match_id in requeued:
            _find_match(tournament, placement.match_id)[2].requeued_at = None


def start_tournament(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    expected_draw_counter: int,
    expected_seed_order: Sequence[UUID],
    clock: Clock,
) -> TournamentView:
    """Generate the schedule and start the tournament (FR-035).

    The request carries the draw counter and the seed order the review screen
    showed: a started tournament is 409 `tournament_not_in_setup`, a stale
    counter 409 `draw_counter_changed`, so a repeat never starts twice
    (ADR-008). A hand reordering of the seeds leaves the counter (ADR-010), so
    a seed order that is not the entries' current one, seed 1 first, is 409
    `seed_order_changed`: the schedule is never drawn from a setup the
    organizer did not see. The seeds follow the entries, so the same check
    covers a change to the players or to their pairs. A round robin, a Swiss
    and a knockout without a group phase are generated so far; Monster DYP is
    422 `format_not_supported`. An incomplete setup is a 422 (`_check_ready`).

    The round robin follows the seeds (BR-050 to BR-052); a Swiss gets round 1
    only, top half of the seeds against the bottom half, the lowest seed
    sitting out with an odd number (BR-055, BR-058), and its later rounds are
    added one at a time (`add_round`, FR-040). Every main entry gets a
    participation row in every round (D5). A knockout without a group phase
    (FR-031) is drawn from the setup seeds into the setup's phase: every
    bracket match at once, the byes for the top seeds in round 1 and the
    third-place match in the final's round (BR-040 to BR-044); only the first
    round stores its sides (D4). The first matches take the free fields in
    schedule order (BR-130). The draws stay as they are (ADR-010).
    """
    _, tournament = _lock_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user_id,
        rounds=True,
    )
    if tournament.state is not TournamentState.SETUP:
        raise ConflictError(ErrorCode.TOURNAMENT_NOT_IN_SETUP, state=tournament.state)
    if tournament.draw_counter != expected_draw_counter:
        raise ConflictError(
            ErrorCode.DRAW_COUNTER_CHANGED, draw_counter=tournament.draw_counter
        )
    phase = tournament.phases[0]  # setup holds exactly one phase (D9)
    _check_ready(tournament, phase)
    main = _main_entries(tournament)
    if list(expected_seed_order) != _seed_order_of(main):
        raise ConflictError(ErrorCode.SEED_ORDER_CHANGED)
    if phase.kind is PhaseKind.KNOCKOUT:
        now = clock()
        bracket = _bracket_from_seeds(main, phase)
        phase.rounds.extend(
            _bracket_rounds(bracket, {entry.id: entry.members for entry in main}, now)
        )
        tournament.state = TournamentState.IN_PROGRESS
        tournament.updated_at = now
        session.flush()  # the matches exist before a field references one
        _fill_fields(tournament, _match_slots(tournament), now)
        session.flush()
        return read_tournament(
            session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
        )
    members = {
        entry.id: sorted(member.player_id for member in entry.members) for entry in main
    }
    schedule = _group_schedule(main, phase)
    now = clock()
    rows = _schedule_rows(phase, schedule, members, now)
    _insert_schedule(session, rows)  # the matches exist before a field references one
    tournament.state = TournamentState.IN_PROGRESS
    tournament.updated_at = now
    _fill_fields(tournament, rows.slots, now)
    session.flush()
    return read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )


def _seed_order_of(main: Sequence[Entry]) -> list[UUID]:
    """The main entries' ids, seed 1 first: what the preview and the start agree on."""
    return list[UUID](seed_order((EntryId(entry.id), entry.seed) for entry in main))


@dataclass(frozen=True, slots=True, kw_only=True)
class StartProblem:
    """Why "Generate and start" would be refused: the code and detail of its 422."""

    code: ErrorCode
    detail: dict[str, JsonValue]


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviewMatch:
    """A match of the preview: the players of each side, a pair in entry order."""

    sides: tuple[tuple[UUID, ...], tuple[UUID, ...]]


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviewRound:
    """A round of the preview; `sitting_out` lists the players of each entry out.

    `byes` lists the players of each entry that goes straight to the second
    round of a knockout, seed 1 first (BR-041); a bye is not a match.
    """

    round_no: int
    matches: tuple[PreviewMatch, ...]
    sitting_out: tuple[tuple[UUID, ...], ...]
    byes: tuple[tuple[UUID, ...], ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class SchedulePreview:
    """What "Generate and start" would create, or why it would not (FR-035).

    With a `problem` there are no rounds, no counts and no `seed_order`.
    `draw_counter` and `seed_order`, the main entries with seed 1 first, are
    the ones the start must carry (ADR-008). A round robin lists all its rounds;
    a Swiss its round 1, without counts, since its rounds come one at a time. A
    knockout without a group phase lists its first round, with the byes, and
    counts every match of the bracket (the third-place match too, no byes)
    and its rounds; `bracket_size` is its number of first-round spots.
    """

    draw_counter: int
    seed_order: tuple[UUID, ...]
    problem: StartProblem | None
    rounds: tuple[PreviewRound, ...]
    match_count: int | None
    round_count: int | None
    bracket_size: int | None

    @property
    def can_start(self) -> bool:
        return self.problem is None


def _start_problem(tournament: Tournament) -> StartProblem | None:
    """The refusal `start_tournament` would answer after its draw counter check."""
    if tournament.state is not TournamentState.SETUP:
        return StartProblem(
            code=ErrorCode.TOURNAMENT_NOT_IN_SETUP, detail={"state": tournament.state}
        )
    try:
        _check_ready(tournament, tournament.phases[0])
    except RuleViolationError as err:
        return StartProblem(code=err.code, detail=err.detail)
    return None


def preview_schedule(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> SchedulePreview:
    """Return what `start_tournament` would create, writing nothing (FR-035).

    Read without a lock, like the setup. The checks and the schedule are the
    start's own (`_check_ready`, `_group_schedule`), so a preview that can start
    is the schedule the start writes for the same draw counter. A refusal comes
    back as the `problem`, not as an error: the review screen shows it. A
    Swiss shows round 1 only and no counts: its later rounds are drawn one at a
    time from the standings (FR-040).
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    tournament = session.scalars(_tournament_query(league, tournament_id)).one_or_none()
    if tournament is None:
        raise NotFoundError(ErrorCode.TOURNAMENT_NOT_FOUND)
    problem = _start_problem(tournament)
    if problem is not None:
        return SchedulePreview(
            draw_counter=tournament.draw_counter,
            seed_order=(),
            problem=problem,
            rounds=(),
            match_count=None,
            round_count=None,
            bracket_size=None,
        )
    setup = _setup_of(
        tournament, _ranking(session, league=league, tournament=tournament)
    )
    players = {entry.id: entry.player_ids for entry in setup.entries}
    phase = tournament.phases[0]
    if phase.kind is PhaseKind.KNOCKOUT:
        return _bracket_preview(
            tournament.draw_counter, _main_entries(tournament), phase, players
        )
    schedule = _group_schedule(_main_entries(tournament), phase)
    rounds = tuple(
        PreviewRound(
            round_no=scheduled.round_no,
            matches=tuple(
                PreviewMatch(sides=(players[m.side_1], players[m.side_2]))
                for m in scheduled.matches
            ),
            sitting_out=()
            if scheduled.sitting_out is None
            else (players[scheduled.sitting_out],),
        )
        for scheduled in schedule
    )
    swiss = phase.format is PhaseFormat.SWISS  # its rounds come one at a time
    return SchedulePreview(
        draw_counter=tournament.draw_counter,
        seed_order=tuple(_seed_order_of(_main_entries(tournament))),
        problem=None,
        rounds=rounds,
        match_count=None if swiss else sum(len(r.matches) for r in rounds),
        round_count=None if swiss else len(rounds),
        bracket_size=None,
    )


def _bracket_preview(
    draw_counter: int,
    main: Sequence[Entry],
    phase: TournamentPhase,
    players: Mapping[UUID, tuple[UUID, ...]],
) -> SchedulePreview:
    """The preview of a knockout without a group phase (BR-040 to BR-044).

    The first round's matches in bracket order, the better seed on side 1, and
    the byes, which are the top seeds, one each (BR-041). The bracket has one
    match fewer than it has entries, and one more with a third-place match.
    """
    bracket = _bracket_from_seeds(main, phase)
    seeds = seed_order((EntryId(entry.id), entry.seed) for entry in main)
    first = bracket.first_round
    return SchedulePreview(
        draw_counter=draw_counter,
        seed_order=tuple(seeds),
        problem=None,
        rounds=(
            PreviewRound(
                round_no=1,
                matches=tuple(
                    PreviewMatch(sides=(players[m.side_1], players[m.side_2]))
                    for m in first
                    if m.side_1 is not None and m.side_2 is not None
                ),
                sitting_out=(),
                byes=tuple(
                    players[entry_id] for entry_id in seeds[: bracket.size - len(seeds)]
                ),
            ),
        ),
        match_count=len(seeds) - 1 + int(bracket.third_place_match),
        round_count=bracket.round_count,
        bracket_size=bracket.size,
    )


def back_to_setup(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    clock: Clock,
) -> TournamentView:
    """Take a started tournament back to setup (FR-036).

    The request expects the tournament in progress; in any other state it is
    409 `tournament_not_in_progress`, so a repeat changes nothing (ADR-008).
    Once a match has a result it is 422 `tournament_has_results`. The rounds,
    with their matches and participation, are deleted and the fields freed: a
    knockout without a group phase keeps its phase, the format of setup, and
    loses its bracket (D4);
    the entries, seeds and draws stay, and every disabled flag is cleared
    (ADR-010, DATA-MODEL §4.4).
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
    results = sum(
        match.outcome is not None
        for phase in tournament.phases
        for round_ in phase.rounds
        for match in round_.matches
    )
    if results:
        raise RuleViolationError(ErrorCode.TOURNAMENT_HAS_RESULTS, results=results)
    now = clock()
    for field in tournament.fields:
        if field.match_id is not None:
            field.match_id = None
            field.updated_at = now
    session.flush()  # the fields let go of the matches before they are deleted
    for phase in tournament.phases:
        phase.rounds.clear()
    for entry in tournament.entries:
        entry.is_disabled = False
    tournament.state = TournamentState.SETUP
    tournament.updated_at = now
    session.flush()
    return read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )


# ---------------------------------------------------------------- results


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


def _match_format(phase: TournamentPhase, round_: Round, match: Match) -> MatchFormat:
    """The format a match plays: its phase's, or the final's own (BR-120).

    The final is the standard match of the bracket's last round (D4).
    """
    is_final = (
        phase.kind is PhaseKind.KNOCKOUT
        and match.kind is MatchKind.STANDARD
        and round_.round_no == max(r.round_no for r in phase.rounds)
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
    422 `result_locked` with the newest `round_no`.
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
    newest, `result_locked` with the newest `round_no` (BR-065); deleting the
    newest round unlocks the one before (BR-066), since the newest round is
    found on every write. A knockout result is locked while a later match it
    feeds has a result, `result_locked` with those `match_ids` (BR-094).
    """
    knockout = knockout_bracket(tournament)
    if knockout is None:
        newest = phase.rounds[-1]
        if phase.format in ROUND_BY_ROUND_FORMATS and round_ is not newest:
            raise RuleViolationError(ErrorCode.RESULT_LOCKED, round_no=newest.round_no)
        return
    if phase.kind is PhaseKind.GROUP:
        raise RuleViolationError(
            ErrorCode.GROUP_PHASE_LOCKED, phase_id=str(knockout.phase.id)
        )
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


# ---------------------------------------------------------------- play


@dataclass(frozen=True, slots=True, kw_only=True)
class BusyField:
    """A field that holds players of a waiting match (BR-131)."""

    field_id: UUID
    player_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class WaitingMatch:
    """A match waiting for a field, with the fields its players are on (FR-092)."""

    match_id: UUID
    busy: tuple[BusyField, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class GroupStandingRow:
    """One entry's line in the group-phase standings, of any format (FR-060).

    A round robin's rows come from BR-101, a Swiss's from BR-070 to BR-074.
    `place` is shared by entries still level (BR-074). `form` and `ahead_by`
    are the round robin's: a Swiss has an empty form and no `ahead_by`, since
    its tie-breakers are the phase's own (FR-043). `bh1` and `bh2` are the
    Swiss's (BR-073), None in a round robin.
    """

    place: int
    entry_id: EntryId
    played: int
    won: int
    drawn: int
    lost: int
    sat_out: int
    points: int
    score_difference: int
    form: tuple[FormResult, ...]
    ahead_by: RoundRobinTiebreaker | None
    bh1: int | None
    bh2: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayView:
    """The running group phase as the play screens read it, computed on read.

    `standings` are the group phase's: a round robin's (BR-101) or a Swiss's
    (BR-070 to BR-074); a Monster DYP has none yet. `group_done` says every
    group-phase match has a result (FR-040); in a Swiss, every match of the
    newest round, since the rounds before it are complete.
    """

    waiting: tuple[WaitingMatch, ...]
    standings: tuple[GroupStandingRow, ...]
    group_done: bool


def _group_phase(tournament: Tournament) -> TournamentPhase | None:
    return next((p for p in tournament.phases if p.kind is PhaseKind.GROUP), None)


def _played_match(match: Match) -> PlayedMatch:
    """A round-robin match with its result, as the standings read it."""
    side_1, side_2 = (side.entry_id for side in match.sides)
    if side_1 is None or side_2 is None or match.outcome is None:
        msg = f"match {match.id} has no result between two entries"
        raise ValueError(msg)
    return PlayedMatch(
        side_1=EntryId(side_1),
        side_2=EntryId(side_2),
        outcome=match.outcome,
        scores=tuple(
            (game.score_1, game.score_2)
            for game in match.games
            if game.score_1 is not None and game.score_2 is not None
        ),
    )


def _standings_of(
    tournament: Tournament, phase: TournamentPhase
) -> tuple[StandingRow, ...]:
    """The round robin's standings now (BR-070, BR-101).

    A sit-out is counted once every match of its round has a result: the schedule
    holds every round from the start, and a sit-out in a round still to come
    has not happened yet. It earns no points in a round robin (BR-071).
    """
    main = sorted(
        _main_entries(tournament), key=lambda e: (e.seed is None, e.seed or 0, e.id)
    )
    return round_robin_standings(
        (EntryId(entry.id) for entry in main),
        matches=[
            _played_match(match)
            for round_ in phase.rounds
            for match in round_.matches
            if match.outcome is not None
        ],
        sit_outs=[
            EntryId(row.entry_id)
            for round_ in phase.rounds
            if all(match.outcome is not None for match in round_.matches)
            for row in round_.participation
            if row.status is Participation.SAT_OUT
        ],
    )


def _swiss_rounds(phase: TournamentPhase) -> tuple[SwissRound, ...]:
    """A Swiss phase's stored rounds as the engine reads them (D5, D11).

    A match's score difference sums the games that have a score (BR-073); a
    walkover has none. The entries sitting a round out are its `sat_out` rows;
    a disabled or not yet joined entry is in neither list (BR-064, BR-067).
    """
    rounds: list[SwissRound] = []
    for round_ in phase.rounds:
        matches: list[SwissMatch] = []
        for match in round_.matches:
            side_1, side_2 = (side.entry_id for side in match.sides)
            if side_1 is None or side_2 is None:
                msg = f"Swiss match {match.id} has a side without an entry"
                raise ValueError(msg)
            matches.append(
                SwissMatch(
                    side_1=EntryId(side_1),
                    side_2=EntryId(side_2),
                    outcome=None
                    if match.outcome is None
                    else MatchOutcome(match.outcome),
                    score_difference=sum(
                        game.score_1 - game.score_2
                        for game in match.games
                        if game.score_1 is not None and game.score_2 is not None
                    ),
                )
            )
        rounds.append(
            SwissRound(
                round_no=round_.round_no,
                matches=tuple(matches),
                sat_out=tuple(
                    EntryId(row.entry_id)
                    for row in sorted(round_.participation, key=lambda r: r.entry_id)
                    if row.status is Participation.SAT_OUT
                ),
            )
        )
    return tuple(rounds)


def _swiss_standings_of(
    tournament: Tournament, phase: TournamentPhase
) -> tuple[SwissStanding, ...]:
    """The Swiss standings now, by position (BR-070 to BR-074, BR-076, FR-043).

    Every main entry is in them, disabled ones included (BR-064). A sit-out
    earns the phase's points as soon as its round is drawn (BR-076); the
    tie-breakers are the phase's, in its order; the lot uses the tournament's
    seed (ADR-010).
    """
    return swiss_standings(
        (EntryId(entry.id) for entry in _main_entries(tournament)),
        _swiss_rounds(phase),
        tiebreakers=[Tiebreaker(t) for t in phase.tiebreakers or ()],
        sit_out_points=phase.sit_out_points or 0,  # the CHECK sets it for Swiss
        rng_seed=tournament.rng_seed,
    )


def group_standings(
    tournament: Tournament, phase: TournamentPhase
) -> tuple[GroupStandingRow, ...]:
    """The group phase's standings now, best first (FR-060, ADR-009).

    A round robin's by BR-101 (`_standings_of`), a Swiss's by BR-070 to
    BR-074 (`_swiss_standings_of`). A Monster DYP has none yet.
    """
    match phase.format:
        case PhaseFormat.ROUND_ROBIN:
            return tuple(
                GroupStandingRow(
                    place=row.place,
                    entry_id=row.entry_id,
                    played=row.played,
                    won=row.won,
                    drawn=row.drawn,
                    lost=row.lost,
                    sat_out=row.sat_out,
                    points=row.points,
                    score_difference=row.score_difference,
                    form=row.form,
                    ahead_by=row.ahead_by,
                    bh1=None,
                    bh2=None,
                )
                for row in _standings_of(tournament, phase)
            )
        case PhaseFormat.SWISS:
            return tuple(
                GroupStandingRow(
                    place=row.place,
                    entry_id=row.entry_id,
                    played=row.played,
                    won=row.won,
                    drawn=row.drawn,
                    lost=row.lost,
                    sat_out=row.sat_out,
                    points=row.points,
                    score_difference=row.score_difference,
                    form=(),
                    ahead_by=None,
                    bh1=row.bh1,
                    bh2=row.bh2,
                )
                for row in _swiss_standings_of(tournament, phase)
            )
        case PhaseFormat.MONSTER_DYP | PhaseFormat.SINGLE_ELIMINATION:
            return ()
        case _:
            assert_never(phase.format)


def tie_groups(rows: Iterable[GroupStandingRow]) -> tuple[tuple[EntryId, ...], ...]:
    """The standings as tie groups by place, best first (BR-074, BR-103).

    The knockout's cut and the places take these; where a strict order is
    needed, they apply their own lot (BR-074).
    """
    groups: dict[int, list[EntryId]] = {}
    for row in rows:
        groups.setdefault(row.place, []).append(row.entry_id)
    return tuple(tuple(groups[place]) for place in sorted(groups))


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


def read_play(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> PlayView:
    """Return the waiting list, the standings and the phase's end (FR-040, FR-060, FR-092).

    Read without a lock. Each waiting match names the fields its players are
    on, which is why it waits (BR-131). A field that points at a match the read
    did not see counts as free.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    tournament = _load_tournament(session, league=league, tournament_id=tournament_id)
    slots = _match_slots(tournament)
    players = {slot.match_id: slot.player_ids or frozenset() for slot in slots}
    # The tournament is read in separate queries, so a write that commits between
    # them can leave a field pointing at a match that was not loaded; such a field
    # counts as free instead of failing the read.
    fields = [
        replace(field, match_id=None)
        if field.match_id is not None and field.match_id not in players
        else field
        for field in sorted(_field_slots(tournament), key=lambda f: f.number)
    ]
    on_fields = [
        (field.field_id, players[field.match_id])
        for field in fields
        if field.match_id is not None
    ]
    waiting = tuple(
        WaitingMatch(
            match_id=slot.match_id,
            busy=tuple(
                BusyField(field_id=field_id, player_ids=tuple(sorted(shared)))
                for field_id, on_field in on_fields
                if (shared := players[slot.match_id] & on_field)
            ),
        )
        for slot in waiting_order(matches=slots, fields=fields)
    )
    group = _group_phase(tournament)
    return PlayView(
        waiting=waiting,
        standings=() if group is None else group_standings(tournament, group),
        group_done=group is not None and bool(group.rounds) and _is_done(group),
    )


# ---------------------------------------------------------------- fields


@dataclass(frozen=True, slots=True, kw_only=True)
class FieldPlacement:
    """A match placed by hand: on a field, or back to waiting with no field (FR-093).

    `from_field_id` is the field the screen saw the match on, None for waiting.
    """

    match_id: UUID
    field_id: UUID | None
    from_field_id: UUID | None


def _lock_running(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> Tournament:
    """Lock a tournament in progress, with its rounds, for a change to its fields.

    Fields are added, removed and given matches while the tournament runs
    (FR-090); in setup or once finished it is 409 `tournament_not_in_progress`.
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
    return tournament


def add_field(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    number: int,
    clock: Clock,
) -> FieldView:
    """Add a field; it takes the next waiting match at once (FR-090, BR-132).

    The request carries the number it expects the field to get, the lowest
    free one (ADR-008). Any other number, a repeat included, is 409
    `field_number_changed` with the `number` a new field would get now, null
    once every number up to 32 is taken.
    """
    tournament = _lock_running(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    expected = next_field_number(field.number for field in tournament.fields)
    if number != expected:
        raise ConflictError(ErrorCode.FIELD_NUMBER_CHANGED, number=expected)
    now = clock()
    field = Field(id=uuid7(), number=number, created_at=now)
    tournament.fields.append(field)
    _fill_fields(tournament, _match_slots(tournament), now)
    session.flush()
    return FieldView(id=field.id, number=field.number, match_id=field.match_id)


def remove_field(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    field_id: UUID,
    user_id: UUID,
    clock: Clock,
) -> None:
    """Remove a field by its id; the others keep their numbers (FR-090, BR-132).

    The match on it goes to the front of the waiting list (`requeued_at`),
    and the free fields are filled, so it can take another free field at
    once. An unknown field, one of another tournament or a repeated delete is
    404 `field_not_found`; the last field is 422 `last_field`.
    """
    tournament = _lock_running(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    field = next((f for f in tournament.fields if f.id == field_id), None)
    if field is None:
        raise NotFoundError(ErrorCode.FIELD_NOT_FOUND)
    if len(tournament.fields) == 1:
        raise RuleViolationError(ErrorCode.LAST_FIELD)
    now = clock()
    if field.match_id is not None:
        _find_match(tournament, field.match_id)[2].requeued_at = now
    tournament.fields.remove(field)
    session.flush()  # the field lets go of its match before another field takes it
    _fill_fields(tournament, _match_slots(tournament), now)
    session.flush()


def _check_placements(
    tournament: Tournament, placements: Sequence[FieldPlacement]
) -> None:
    """Refuse placements the current state does not allow (ADR-008, FR-093).

    Unknown ids are 404. A match with a result, a match that is not where the
    screen saw it (`from_field_id`) or a field that holds a match the request
    does not name only reach here from a stale screen: 409. A side not known
    yet, or a bye, is 422 `match_sides_unknown` (BR-091). Of what is left,
    only the four operations of FR-093 are allowed (`_refuse_other_operations`).
    """
    fields = {field.id: field for field in tournament.fields}
    named = {placement.match_id for placement in placements}
    found = [
        (_find_match(tournament, placement.match_id)[2], placement)
        for placement in placements
    ]
    if any(p.field_id is not None and p.field_id not in fields for p in placements):
        raise NotFoundError(ErrorCode.FIELD_NOT_FOUND)
    players = _match_players(tournament)
    for match, _ in found:
        if match.outcome is not None:
            raise ConflictError(ErrorCode.MATCH_HAS_RESULT, match_id=str(match.id))
        if players[match.id] is None or any(side.is_bye for side in match.sides):
            raise RuleViolationError(ErrorCode.MATCH_SIDES_UNKNOWN)
    seen = {f.match_id: f.id for f in tournament.fields if f.match_id is not None}
    if any(seen.get(p.match_id) != p.from_field_id for p in placements):
        raise ConflictError(ErrorCode.PLACEMENT_CHANGED)
    for placement in placements:
        if placement.field_id is None:
            continue
        held = fields[placement.field_id].match_id
        if held is not None and held not in named:
            raise ConflictError(
                ErrorCode.FIELD_NOT_FREE,
                field_id=str(placement.field_id),
                match_id=str(held),
            )
    _refuse_other_operations(placements)


def _refuse_other_operations(placements: Sequence[FieldPlacement]) -> None:
    """Allow only the four operations of FR-093, else 422 `placement_not_allowed`.

    A waiting match on a free field, a match from its field to a free field,
    a match back to waiting, and a swap of two matches that are both on
    fields. Replacing the match on a field and a rotation are not allowed
    until the PRD decides whether they should exist. A free target field is
    checked before (`field_not_free`), so a single placement only has to
    change something.
    """
    if len(placements) == 1:
        (only,) = placements
        allowed = only.field_id != only.from_field_id
    else:
        first, second = placements
        allowed = (
            first.from_field_id is not None
            and second.from_field_id is not None
            and first.field_id == second.from_field_id
            and second.field_id == first.from_field_id
        )
    if not allowed:
        raise RuleViolationError(ErrorCode.PLACEMENT_NOT_ALLOWED)


def _store_fields(
    session: Session,
    tournament: Tournament,
    placed: Iterable[FieldSlot],
    now: datetime,
) -> None:
    """Write each field's match; a match that takes a field is no longer requeued."""
    rows = {field.id: field for field in tournament.fields}
    changed = [
        (rows[slot.field_id], slot.match_id)
        for slot in placed
        if rows[slot.field_id].match_id != slot.match_id
    ]
    if not changed:
        return
    for field, _ in changed:
        field.match_id = None
    # A match moving to another field leaves the old one first: `fields.match_id`
    # is unique, and a swap would hold one match on two fields in between.
    session.flush()
    for field, match_id in changed:
        field.match_id = match_id
        field.updated_at = now
        if match_id is not None:
            _find_match(tournament, match_id)[2].requeued_at = None


def place_matches(
    session: Session,
    *,
    league_id: UUID,
    tournament_id: UUID,
    user_id: UUID,
    placements: Sequence[FieldPlacement],
    clock: Clock,
) -> TournamentView:
    """Place, move, swap or take off matches by hand, the target state (FR-093).

    Each named match ends on its named field, or waiting without one; a swap
    names both matches with their new fields (ADR-008). A field that a match leaves and that is not named takes the
    next waiting match, but not one this request sends back to waiting: that
    one waits in schedule order (DATA-MODEL §4.6). The filling never moves a
    match on a field, so a placement by hand holds until its result (BR-133).

    Refusals: `_check_placements`, then 422 `player_on_another_field` when a
    player would be on two fields at once (BR-131).
    """
    tournament = _lock_running(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user_id
    )
    _check_placements(tournament, placements)
    try:
        placed = place_by_hand(
            matches=_match_slots(tournament),
            fields=_field_slots(tournament),
            placements=[
                HandPlacement(
                    match_id=MatchId(p.match_id),
                    field_id=None if p.field_id is None else FieldId(p.field_id),
                )
                for p in placements
            ],
        )
    except EngineError as err:
        raise to_app_error(err) from err
    _store_fields(session, tournament, placed, clock())
    session.flush()
    return read_tournament(
        session, league_id=league_id, tournament_id=tournament.id, user_id=user_id
    )


# ---------------------------------------------------------------- Swiss rounds


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
) -> RoundView:
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
    (BR-065), and its first matches take the free fields (BR-130).
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
    return next(round_ for round_ in view.rounds if round_.id == round_id)


# ---------------------------------------------------------------- finishing


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


type PlaceKind = Literal[
    "won_final",
    "lost_final",
    "won_third_place",
    "lost_third_place",
    "lost_in_round",
    "group_place",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaceView:
    """An entry's final place and what each of its players earns (BR-100, BR-110).

    `kind` says why: the final, the third-place match, the knockout round the
    entry went out in (`round`, with the `score` of that match from the
    entry's side and the `opponent_entry_id`), or, for an entry that did not
    go through, its place in the group phase (BR-102, BR-103). `group_place`
    is the entry's place in the group-phase standings, a knockout entry's
    that of the entry it continues; null without a group phase.
    """

    place: int
    entry_id: UUID
    points_per_player: int
    kind: PlaceKind
    round: RoundName | None
    score: tuple[int, int] | None
    opponent_entry_id: UUID | None
    group_place: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PlacesView:
    """The places of a finished tournament; none before it finishes."""

    complete: bool
    group_format: PhaseFormat | None
    rows: tuple[PlaceView, ...]


def _require_played_group(tournament: Tournament) -> TournamentPhase:
    """The round robin or Swiss of a tournament, with or without a knockout after it.

    Monster DYP is not played yet: 422 `format_not_supported` until it is.
    """
    group = _group_phase(tournament)
    if group is None or group.format not in PLAYED_GROUP_FORMATS:
        last = tournament.phases[-1]
        raise RuleViolationError(ErrorCode.FORMAT_NOT_SUPPORTED, format=last.format)
    return group


def _placing_entries(tournament: Tournament) -> list[PlacingEntry]:
    return [
        PlacingEntry(
            entry_id=EntryId(entry.id),
            player_ids=tuple(PlayerId(m.player_id) for m in entry.members),
            seed=entry.seed,
        )
        for entry in tournament.entries
    ]


def knockout_places(
    tournament: Tournament,
    standings: Sequence[GroupStandingRow],
    knockout: KnockoutBracket,
) -> tuple[EntryPlace, ...]:
    """Place a tournament whose knockout has every result (BR-102, BR-103).

    The knockout entries take the top places, and the entries that did not go
    through follow in their group-phase order, numbered after them.
    """
    return place_entries(
        _placing_entries(tournament),
        standing=tie_groups(standings),
        knockout=knockout_results(knockout.played.values()),
        third_place_match=knockout.bracket.third_place_match,
    )


def _score_for(match: Match, entry_side: int) -> tuple[int, int] | None:
    """A result from one side's view: a BO1 game's goals, else the games won.

    A walkover has no score (BR-124), nor a BO1 game without one.
    """
    if match.is_walkover or not match.games:
        return None
    own, other = (Outcome.SIDE_1, Outcome.SIDE_2)[:: 1 if entry_side == 1 else -1]
    if len(match.games) == 1:
        game = match.games[0]
        if game.score_1 is None or game.score_2 is None:
            return None
        goals = (game.score_1, game.score_2)
        return goals if entry_side == 1 else (goals[1], goals[0])
    return (
        sum(game.winner is own for game in match.games),
        sum(game.winner is other for game in match.games),
    )


def _knockout_reason(
    entry_id: UUID, knockout: KnockoutBracket
) -> tuple[PlaceKind, RoundName, tuple[int, int] | None, UUID | None]:
    """Why a knockout entry has its place: the last match it played (BR-102)."""
    last = max(
        (
            match
            for match in knockout.played.values()
            if entry_id in {match.winner, match.loser} and match.loser is not None
        ),
        key=lambda match: match.key,
    )
    won = last.winner == entry_id
    if last.key.is_third_place:
        kind: PlaceKind = "won_third_place" if won else "lost_third_place"
    elif last.key == knockout.bracket.final:
        kind = "won_final" if won else "lost_final"
    else:
        kind = "lost_in_round"
    side = 1 if last.side_1.entry_id == entry_id else 2
    opponent = (last.side_2 if side == 1 else last.side_1).entry_id
    return (
        kind,
        round_name(last.key.round_no, knockout.bracket.round_count),
        _score_for(knockout.rows[last.key], side),
        opponent,
    )


def read_places(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> PlacesView:
    """Return the places and season points of a finished tournament (§7.13, §7.14).

    See `view_places`.
    """
    league = get_league(session, league_id=league_id, user_id=user_id)
    return view_places(session, league=league, tournament_id=tournament_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Placed:
    """A finished tournament's group standings, places and season points."""

    group: TournamentPhase | None
    standings: tuple[GroupStandingRow, ...]
    knockout: KnockoutBracket | None
    places: tuple[EntryPlace, ...]
    points: tuple[PlayerPoints, ...]


def _placed(tournament: Tournament, placement_points: Sequence[int]) -> _Placed:
    """Place a finished tournament's entries and give them the table's points.

    Without a knockout the group phase's standings are the places (BR-101,
    BR-103; a Swiss's by BR-072 to BR-074); with one, the knockout entries
    take the top places by BR-102 and the rest follow in their group-phase
    order (BR-103). A knockout without a group phase places every entry by
    BR-102 alone (FR-031). Each player earns the placement points of their
    place, entries sharing a place the average of the places they cover,
    rounded down (BR-110, BR-111). Monster DYP is 422 `format_not_supported`
    until it is played.
    """
    group = _group_phase(tournament)
    knockout = knockout_bracket(tournament)
    if group is None and knockout is not None:
        standings: tuple[GroupStandingRow, ...] = ()  # a knockout from the start
    else:
        group = _require_played_group(tournament)
        standings = group_standings(tournament, group)
    if knockout is None:
        places = place_entries(
            _placing_entries(tournament), standing=tie_groups(standings)
        )
    else:
        places = knockout_places(tournament, standings, knockout)
    return _Placed(
        group=group,
        standings=standings,
        knockout=knockout,
        places=places,
        points=season_points(places, placement_points),
    )


def _season_of(league: League, season_id: UUID) -> Season:
    return next(s for s in league.seasons if s.id == season_id)


def view_places(
    session: Session,
    *,
    league: League,
    tournament_id: UUID,
    past_setup: bool = False,
) -> PlacesView:
    """Return the places and season points of one of the league's tournaments.

    Read without a lock and computed on read (D1), with the season's table
    (BR-110, BR-111). A tournament not yet finished has no places. Without a
    knockout the group phase's standings are the places; with one, the knockout
    entries take the top places by BR-102 and the rest follow in their
    group-phase order (BR-103). With `past_setup`, a tournament in setup is 404
    `tournament_not_found`, like an unknown one (FR-070).
    """
    tournament = _load_tournament(
        session, league=league, tournament_id=tournament_id, past_setup=past_setup
    )
    if tournament.state is not TournamentState.FINISHED:
        return PlacesView(complete=False, group_format=None, rows=())
    placed = _placed(
        tournament, _season_of(league, tournament.season_id).placement_points
    )
    knockout = placed.knockout
    points = {row.entry_id: row.points for row in placed.points}
    group_place = {row.entry_id: row.place for row in placed.standings}
    source = {entry.id: entry.source_entry_id for entry in tournament.entries}
    # The entries the bracket drew: knockout entries after a group phase, the
    # main entries of a knockout without one (FR-031).
    in_bracket = (
        set()
        if knockout is None
        else {
            entry_id
            for match in knockout.bracket.first_round
            for entry_id in (match.side_1, match.side_2)
            if entry_id is not None
        }
    )

    def view(place: EntryPlace) -> PlaceView:
        entry_id = place.entry_id
        in_group = group_place.get(EntryId(source[entry_id] or entry_id))
        if knockout is None or entry_id not in in_bracket:
            return PlaceView(
                place=place.place,
                entry_id=entry_id,
                points_per_player=points.get(entry_id, 0),
                kind="group_place",
                round=None,
                score=None,
                opponent_entry_id=None,
                group_place=in_group,
            )
        kind, round_, score, opponent = _knockout_reason(entry_id, knockout)
        return PlaceView(
            place=place.place,
            entry_id=entry_id,
            points_per_player=points.get(entry_id, 0),
            kind=kind,
            round=round_,
            score=score,
            opponent_entry_id=opponent,
            group_place=in_group,
        )

    return PlacesView(
        complete=True,
        group_format=None if placed.group is None else placed.group.format,
        rows=tuple(view(place) for place in placed.places),
    )


def view_group_standings(
    session: Session, *, league: League, tournament_id: UUID, past_setup: bool = False
) -> tuple[GroupStandingRow, ...]:
    """Return the group phase's standings now: a round robin's or a Swiss's (FR-060).

    The same standings as the play read's (`read_play`); none without a group
    phase or for a Monster DYP. With `past_setup`, a tournament in setup is
    404 `tournament_not_found` (FR-070).
    """
    tournament = _load_tournament(
        session, league=league, tournament_id=tournament_id, past_setup=past_setup
    )
    group = _group_phase(tournament)
    return () if group is None else group_standings(tournament, group)


def finished_season_points(
    session: Session, *, season: Season
) -> dict[UUID, tuple[PlayerPoints, ...]]:
    """The season points of each finished tournament of a season (BR-112).

    Keyed by tournament id, oldest first; computed with the season's table as
    it is now (BR-012). Tournaments that are not finished do not count.
    """
    tournaments = session.scalars(
        select(Tournament)
        .where(
            Tournament.season_id == season.id,
            Tournament.state == TournamentState.FINISHED,
        )
        .options(
            selectinload(Tournament.phases),
            selectinload(Tournament.entries).selectinload(Entry.members),
            _ROUNDS_IN_FULL,
        )
        .order_by(Tournament.date, Tournament.created_at, Tournament.id)
        .execution_options(populate_existing=True)
    ).all()
    return {
        tournament.id: _placed(tournament, season.placement_points).points
        for tournament in tournaments
    }
