"""Tournaments in setup: create, format, players, pairs, halves, seeds (FR-030 to FR-039).

Every write locks the league row, then the tournament row (ADR-008), and loads
every id it is given through them. A change to the entries discards the seeding
and draws again where the inputs are complete, incrementing the draw counter
(ADR-010).
"""

import secrets
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid7

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from tourneyhub.db.models.entries import Entry, EntryMember, PlayerHalf
from tourneyhub.db.models.leagues import League, Player, Season
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
from tourneyhub.engine.ids import EntryId, PlayerId
from tourneyhub.engine.leagues import SeasonState
from tourneyhub.engine.lots import RNG_SEED_SIZE
from tourneyhub.engine.ranking import PlayerRecord, RankedPlayer, rank_league
from tourneyhub.engine.seeding import SeedingEntry, seed_by_lot, seed_by_ranking
from tourneyhub.engine.tournaments import (
    DEFAULT_TIEBREAKERS,
    EntryKind,
    EntryStage,
    GroupPhase,
    HalvesMethod,
    KnockoutMatchFormat,
    MatchFormat,
    PhaseFormat,
    PhaseKind,
    SeedingMethod,
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
    league's defaults (FR-030, DATA-MODEL §4.2); `round_robin_legs` is 1,
    `sit_out_points` 0 (FR-039) and `third_place_match` false.
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
class TournamentSummary:
    """A tournament in its season's list (screen 1).

    The progress, the winner and the current phase come from rounds and
    results; a tournament has none of them until it is generated.
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
    progress: None
    winner_player_ids: tuple[UUID, ...] | None


# ---------------------------------------------------------------- loading


def _tournament_query(league: League, tournament_id: UUID) -> Select[Tournament]:
    """A tournament of the league with what setup reads (ADR-008)."""
    return (
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


def _lock_tournament(
    session: Session, *, league_id: UUID, tournament_id: UUID, user_id: UUID
) -> tuple[League, Tournament]:
    """Lock the league, then one of its tournaments (ADR-008).

    Another organizer's league is 404 `league_not_found`; a tournament of
    another league, or an unknown one, is 404 `tournament_not_found`.
    """
    league = lock_league(session, league_id=league_id, user_id=user_id)
    tournament = session.scalars(
        _tournament_query(league, tournament_id).with_for_update(of=Tournament)
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


def _ranking(
    session: Session, *, league: League, tournament: Tournament
) -> tuple[RankedPlayer, ...]:
    """The league ranking of the players on the list, for this tournament (BR-020).

    The final lot uses the tournament's seed (ADR-010). Season points, wins and
    last season's place come from finished tournaments, which cannot exist yet:
    a tournament only finishes once it has been generated and played (FR-035,
    FR-037), so every player has none.
    """
    player_ids = session.scalars(
        select(Player.id).where(
            Player.league_id == league.id, Player.removed_at.is_(None)
        )
    ).all()
    return rank_league(
        (
            PlayerRecord(
                player_id=PlayerId(player_id),
                season_points=0,
                tournament_wins=0,
                last_season_place=None,
            )
            for player_id in player_ids
        ),
        rng_seed=tournament.rng_seed,
    )


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
            RankingRow(rank=ranked.position, player_id=ranked.player_id, points=0)
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
    if all(season.id != season_id for season in league.seasons):
        raise NotFoundError(ErrorCode.SEASON_NOT_FOUND)
    tournaments = session.scalars(
        select(Tournament)
        .where(Tournament.season_id == season_id)
        .options(
            selectinload(Tournament.phases),
            selectinload(Tournament.players),
            selectinload(Tournament.entries).selectinload(Entry.members),
        )
        .order_by(Tournament.date.desc(), Tournament.created_at.desc(), Tournament.id)
    ).all()
    return [_summary_of(tournament) for tournament in tournaments]


def _summary_of(tournament: Tournament) -> TournamentSummary:
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
        current_phase_id=None,
        current_phase_done=False,
        player_count=player_count,
        progress=None,
        winner_player_ids=None,
    )


# ---------------------------------------------------------------- format


def _resolve_format(request: FormatRequest, league: League) -> TournamentFormat:
    """Fill in what the request left out from the league's defaults (FR-030).

    BO2 needs a league that allows draws (BR-121): 422 `draws_not_allowed`.
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
        resolved = replace(
            base,
            round_robin_legs=(request.round_robin_legs or 1)
            if request.group_phase is GroupPhase.ROUND_ROBIN
            else None,
            sit_out_points=request.sit_out_points or 0,
            group_match_format=request.group_match_format
            or MatchFormat(default_format),
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
    Monster DYP phase start at FR-043's default and stay while its format does.
    """
    settings = _phase_settings(fmt)
    phase = next(iter(tournament.phases), None)
    if phase is not None and phase.kind is not settings["kind"]:
        tournament.phases.remove(phase)
        session.flush()  # free position 1 before the new phase takes it
        phase = None
    if phase is None:
        phase = TournamentPhase(id=uuid7(), position=1, created_at=now)
        tournament.phases.append(phase)
    elif all(getattr(phase, column) == value for column, value in settings.items()):
        return False
    else:
        phase.updated_at = now
    for column, value in settings.items():
        setattr(phase, column, value)
    keeps_tiebreakers = phase.tiebreakers is not None and settings["format"] in {
        PhaseFormat.SWISS,
        PhaseFormat.MONSTER_DYP,
    }
    if not keeps_tiebreakers:
        phase.tiebreakers = (
            list(DEFAULT_TIEBREAKERS)
            if settings["format"] in {PhaseFormat.SWISS, PhaseFormat.MONSTER_DYP}
            else None
        )
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
        missing = min(ids - {player.id for player in players})
        raise NotFoundError(ErrorCode.PLAYER_NOT_FOUND, player_id=str(missing))
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

    A removed player cannot be picked (BR-002): 422 `player_removed`. A changed
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
        raise RuleViolationError(ErrorCode.PLAYER_REMOVED, player_id=str(removed[0]))
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
