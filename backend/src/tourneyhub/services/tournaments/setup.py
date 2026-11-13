"""Creating a tournament, setting its format and deleting it."""

import secrets
from dataclasses import dataclass, replace
from datetime import date, datetime
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League
from tourneyhub.db.models.tournaments import Field, Tournament, TournamentPhase
from tourneyhub.engine.leagues import SeasonState
from tourneyhub.engine.lots import RNG_SEED_SIZE
from tourneyhub.engine.tournaments import (
    DEFAULT_SIT_OUT_POINTS,
    DEFAULT_TIEBREAKERS,
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
)
from tourneyhub.errors import ConflictError, ErrorCode, RuleViolationError
from tourneyhub.services.leagues import active_season, lock_league
from tourneyhub.services.tournaments.entries import _discard_entries, _new_draw
from tourneyhub.services.tournaments.places import _ranking
from tourneyhub.services.tournaments.shared import Clock, _lock_setup, _lock_tournament
from tourneyhub.services.tournaments.views import (
    TournamentFormat,
    TournamentSetup,
    _setup_of,
    read_tournament_setup,
)


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
