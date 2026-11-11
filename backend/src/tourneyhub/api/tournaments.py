from datetime import date, datetime
from http import HTTPStatus
from typing import Annotated, Literal, Self
from uuid import UUID

from fastapi import APIRouter
from pydantic import UUID7, AfterValidator, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from tourneyhub.api.deps import ClockDep, CurrentUserDep, SessionDep
from tourneyhub.api.schemas import INT_MAX, ErrorResponse, RequestModel, ResponseModel
from tourneyhub.engine.dyp import DypHalf
from tourneyhub.engine.leagues import (
    MAX_FIELD_COUNT,
    MAX_GOALS_PER_GAME,
    MAX_PLAYERS_PER_LEAGUE,
)
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
    PhaseFormat,
    PhaseKind,
    SeedingMethod,
    Tiebreaker,
    TournamentState,
    TournamentType,
)
from tourneyhub.services import tournaments as tournament_service
from tourneyhub.services.tournaments import DrawTarget, FormatRequest

router = APIRouter(
    prefix="/leagues/{league_id}",
    tags=["tournaments"],
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ErrorResponse},
        HTTPStatus.NOT_FOUND: {"model": ErrorResponse},
    },
)

_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    HTTPStatus.CONFLICT: {"model": ErrorResponse},
    HTTPStatus.UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}

type TournamentName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
type GoalsPerGame = Annotated[int, Field(ge=1, le=MAX_GOALS_PER_GAME)]
type FieldCount = Annotated[int, Field(ge=1, le=MAX_FIELD_COUNT)]


def _distinct[T](values: list[T]) -> list[T]:
    if len(set(values)) != len(values):
        raise PydanticCustomError("given_twice", "an id is given twice")
    return values


def _distinct_players(pairs: list[tuple[UUID, UUID]]) -> list[tuple[UUID, UUID]]:
    _distinct([player for pair in pairs for player in pair])
    return pairs


# A league holds at most 500 players, so no list of its players or entries is longer.
type PlayerIds = Annotated[
    list[UUID], Field(max_length=MAX_PLAYERS_PER_LEAGUE), AfterValidator(_distinct)
]

_GROUP_SETTINGS = ("round_robin_legs", "sit_out_points", "group_match_format")
_KNOCKOUT_SETTINGS = (
    "knockout_match_format",
    "final_match_format",
    "third_place_match",
)


class _FormatChecks(RequestModel):
    name: TournamentName
    date: date
    type: TournamentType
    group_phase: GroupPhase

    def _check(self, *, complete: bool) -> Self:
        """FR-031: the settings that apply to the chosen phases, and no others.

        Monster DYP always plays its own rounds, and no other type does. With a
        group phase, its settings apply; without one, the knockout's. With
        `complete`, every setting that applies must be given (`final_match_format`
        may be null: the final plays the knockout's format).
        """
        if (self.type is TournamentType.MONSTER_DYP) != (
            self.group_phase is GroupPhase.MONSTER_DYP
        ):
            raise PydanticCustomError(
                "group_phase_mismatch", "the group phase does not fit the type"
            )
        grouped = self.group_phase is not GroupPhase.NONE
        applies = set(_GROUP_SETTINGS if grouped else _KNOCKOUT_SETTINGS)
        if self.group_phase is not GroupPhase.ROUND_ROBIN:
            applies.discard("round_robin_legs")
        for name in (*_GROUP_SETTINGS, *_KNOCKOUT_SETTINGS):
            value = getattr(self, name)
            if name not in applies and value is not None:
                raise PydanticCustomError(
                    "setting_not_applicable", "a setting does not fit the phases"
                )
            if complete and name in applies - {"final_match_format"} and value is None:
                raise PydanticCustomError("setting_missing", "a setting is missing")
        return self


class TournamentFormatWrite(_FormatChecks):
    """The whole format of a tournament in setup, the target state (FR-030, FR-031).

    With a group phase (`round_robin`, `swiss`, `monster_dyp`) its settings are
    given and the knockout's are null: a knockout after a group phase is set up
    when it starts (FR-045). With `none` the knockout's settings are given and
    the group phase's are null. `round_robin_legs` is only for a round robin.
    A setting that does not apply is 422 `validation_failed` with
    `setting_not_applicable`; one that applies and is missing, `setting_missing`.
    """

    round_robin_legs: Literal[1, 2] | None
    sit_out_points: Literal[0, 1] | None
    group_match_format: MatchFormat | None
    knockout_match_format: KnockoutMatchFormat | None
    final_match_format: KnockoutMatchFormat | None
    third_place_match: bool | None
    goals_per_game: GoalsPerGame
    field_count: FieldCount

    @model_validator(mode="after")
    def _settings_fit_the_phases(self) -> Self:
        return self._check(complete=True)


class TournamentCreate(_FormatChecks):
    """A new tournament in the league's active season (FR-030).

    `id` is a UUIDv7 made by the client; a repeat gets the same tournament back
    (ADR-008). A setting left out or null takes the league's default: goals per
    game, the number of fields and the match format of the phase (FR-011); one
    round robin leg, no sit-out points (FR-039) and no third-place match.
    """

    id: UUID7
    round_robin_legs: Literal[1, 2] | None = None
    sit_out_points: Literal[0, 1] | None = None
    group_match_format: MatchFormat | None = None
    knockout_match_format: KnockoutMatchFormat | None = None
    final_match_format: KnockoutMatchFormat | None = None
    third_place_match: bool | None = None
    goals_per_game: GoalsPerGame | None = None
    field_count: FieldCount | None = None

    @model_validator(mode="after")
    def _settings_fit_the_phases(self) -> Self:
        return self._check(complete=False)


class PlayersWrite(RequestModel):
    """The players picked for the tournament, the target state (FR-032)."""

    player_ids: PlayerIds


class PairsWrite(RequestModel):
    """A Doubles tournament's pairs, the target state (FR-033, BR-003, BR-030).

    No player twice (`given_twice`); picked players left out have no partner yet.
    """

    pairs: Annotated[
        list[tuple[UUID, UUID]],
        Field(max_length=MAX_PLAYERS_PER_LEAGUE // 2),
        AfterValidator(_distinct_players),
    ]


class DypHalfWrite(RequestModel):
    player_id: UUID
    half: DypHalf


def _distinct_halves(halves: list[DypHalfWrite]) -> list[DypHalfWrite]:
    _distinct([half.player_id for half in halves])
    return halves


class HalvesWrite(RequestModel):
    """How a DYP tournament's halves are made (FR-033, BR-032).

    `ranking` ignores `halves`. `by_hand` sets them as the target state; a
    picked player without a row has no half yet.
    """

    method: HalvesMethod
    halves: Annotated[
        list[DypHalfWrite],
        Field(max_length=MAX_PLAYERS_PER_LEAGUE),
        AfterValidator(_distinct_halves),
    ]


class SeedingWrite(RequestModel):
    """Seed by league ranking or by random shuffle (FR-034, BR-021, BR-022)."""

    method: SeedingMethod


type EntryIds = Annotated[
    list[UUID], Field(max_length=MAX_PLAYERS_PER_LEAGUE), AfterValidator(_distinct)
]


class SeedOrderWrite(RequestModel):
    """Every main entry, seed 1 first: the full order, never a move (ADR-008)."""

    entry_ids: EntryIds


class DrawWrite(RequestModel):
    """A new draw, with the draw counter the screen showed (ADR-008, ADR-010)."""

    expected_draw_counter: Annotated[int, Field(ge=0, le=INT_MAX)]
    target: DrawTarget


class TournamentFormatRead(ResponseModel):
    """The format as stored; settings that do not apply are null (FR-031)."""

    name: str
    date: date
    type: TournamentType
    group_phase: GroupPhase
    round_robin_legs: Literal[1, 2] | None
    sit_out_points: Literal[0, 1] | None
    group_match_format: MatchFormat | None
    knockout_match_format: KnockoutMatchFormat | None
    final_match_format: KnockoutMatchFormat | None
    third_place_match: bool | None
    goals_per_game: int
    field_count: int


class EntryRead(ResponseModel):
    """An entry: one player, or a pair with its better-ranked player first.

    A DYP pair names its top-half player first. `seed` is null in Monster DYP.
    """

    id: UUID
    stage: EntryStage
    kind: EntryKind
    seed: int | None
    player_ids: list[UUID]
    is_disabled: bool
    is_top_player: bool


class DypHalfRead(ResponseModel):
    player_id: UUID
    half: DypHalf


class RankingRow(ResponseModel):
    """A player's place in the league ranking this tournament uses (BR-020)."""

    rank: int
    player_id: UUID
    points: int


class TournamentSetupRead(ResponseModel):
    """What the setup screens show (FR-030 to FR-034).

    `draw_counter` goes back in "draw again" (ADR-008). `player_ids` are the
    picked players in league-ranking order; `ranking` lists every player on the
    league's list. `entries` are the main entries by seed.
    """

    tournament_id: UUID
    state: TournamentState
    format: TournamentFormatRead
    seeding_method: SeedingMethod
    draw_counter: int
    player_ids: list[UUID]
    halves_method: HalvesMethod
    halves: list[DypHalfRead]
    top_player_ids: list[UUID]
    entries: list[EntryRead]
    ranking: list[RankingRow]


class PhaseSummary(ResponseModel):
    id: UUID
    position: int
    kind: PhaseKind
    format: PhaseFormat


class TournamentProgress(ResponseModel):
    """How far a running tournament is: rounds and matches with results."""

    round_no: int
    round_count: int
    matches_played: int
    match_count: int
    in_knockout: bool


class TournamentSummary(ResponseModel):
    """A tournament in its season's list (screen 1).

    `player_count` counts the picked players in setup, and the players in the
    entries afterwards. `current_phase_id` and `progress` are null, and
    `winner_player_ids` too, until the tournament is generated and finished.
    """

    id: UUID
    season_id: UUID
    name: str
    date: date
    type: TournamentType
    state: TournamentState
    phases: list[PhaseSummary]
    current_phase_id: UUID | None
    current_phase_done: bool
    player_count: int
    progress: TournamentProgress | None
    winner_player_ids: list[UUID] | None


class PhaseRead(ResponseModel):
    """A phase with every setting; those that do not apply are null (FR-031)."""

    id: UUID
    position: int
    kind: PhaseKind
    format: PhaseFormat
    round_robin_legs: Literal[1, 2] | None
    sit_out_points: Literal[0, 1] | None
    tiebreakers: list[Tiebreaker] | None
    qualifiers: int | None
    third_place_match: bool | None
    monster_knockout_mode: MonsterKnockoutMode | None
    match_format: MatchFormat
    final_match_format: KnockoutMatchFormat | None


class GameRead(ResponseModel):
    """One game of a result: its winner and, if entered, its score (D11)."""

    game_no: int
    winner: Outcome
    score_1: int | None
    score_2: int | None


class MatchSideRead(ResponseModel):
    """A side: its entry (null for a Monster DYP team or a bye) and its players.

    A pair's players come in the entry's order.
    """

    entry_id: UUID | None
    player_ids: list[UUID]
    is_bye: bool


class MatchRead(ResponseModel):
    """A match with its two sides and its result; no result yet is null (D11)."""

    id: UUID
    round_id: UUID
    position: int
    kind: MatchKind
    sides: tuple[MatchSideRead, MatchSideRead]
    outcome: Outcome | None
    is_walkover: bool
    games: list[GameRead]
    result_entered_at: datetime | None


class RoundRead(ResponseModel):
    """A round in play order, with the entries that sit it out (BR-051)."""

    id: UUID
    phase_id: UUID
    round_no: int
    matches: list[MatchRead]
    sitting_out: list[UUID]


class FieldRead(ResponseModel):
    """A field and the match being played on it, null while it is free (D10)."""

    id: UUID
    number: int
    match_id: UUID | None


class TournamentRead(ResponseModel):
    """The whole tournament: settings, entries, rounds and fields (FR-035, FR-092).

    `current_phase_id` is the last phase with rounds; `current_phase_done` says
    whether all its matches so far have results. `waiting` lists the matches
    waiting for a field, in the order they will get one, computed on read.
    `entries` are all the tournament's entries as setup shows them: the main
    entries by seed, then the knockout-stage entries. A tournament in setup has
    no rounds.
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
    phases: list[PhaseRead]
    entries: list[EntryRead]
    rounds: list[RoundRead]
    fields: list[FieldRead]
    waiting: list[UUID]


class StartWrite(RequestModel):
    """Generate and start, with the draw counter the review screen showed (ADR-008)."""

    expected_draw_counter: Annotated[int, Field(ge=0, le=INT_MAX)]


class BackToSetupWrite(RequestModel):
    """Back to setup, from the state the screen showed (FR-036, ADR-008)."""

    expected_state: Literal["in_progress"]


@router.get("/seasons/{season_id}/tournaments")
def list_tournaments(
    league_id: UUID, season_id: UUID, session: SessionDep, user: CurrentUserDep
) -> list[TournamentSummary]:
    """List a season's tournaments, newest date first; closed seasons too (FR-022).

    Another league's season is 404 `season_not_found`.
    """
    tournaments = tournament_service.list_tournaments(
        session, league_id=league_id, season_id=season_id, user_id=user.id
    )
    return [TournamentSummary.model_validate(t) for t in tournaments]


@router.post("/tournaments", status_code=HTTPStatus.CREATED, responses=_WRITE_ERRORS)
def create_tournament(
    league_id: UUID,
    body: TournamentCreate,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Create a tournament in setup in the league's active season (FR-030).

    A repeat gets the tournament back. An id that another tournament has, in
    another season or with another type, is 409 `tournament_id_taken`. BO2 in a
    league without draws is 422 `draws_not_allowed` (BR-121).
    """
    setup = tournament_service.create_tournament(
        session,
        league_id=league_id,
        user_id=user.id,
        tournament_id=body.id,
        request=_format_request(body),
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.delete(
    "/tournaments/{tournament_id}",
    status_code=HTTPStatus.NO_CONTENT,
    responses={HTTPStatus.CONFLICT: {"model": ErrorResponse}},
)
def delete_tournament(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> None:
    """Delete a tournament with everything in it, in any state (FR-038).

    The UI asks first. A tournament of a closed season is 409 `season_closed`;
    a repeated delete is 404 `tournament_not_found`, which means it is gone.
    """
    tournament_service.delete_tournament(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )


@router.get("/tournaments/{tournament_id}")
def read_tournament(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> TournamentRead:
    """Return the whole tournament with its rounds and fields (FR-035, FR-092).

    Another league's tournament is 404 `tournament_not_found`.
    """
    tournament = tournament_service.read_tournament(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return TournamentRead.model_validate(tournament)


@router.post("/tournaments/{tournament_id}/start", responses=_WRITE_ERRORS)
def start_tournament(
    league_id: UUID,
    tournament_id: UUID,
    body: StartWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentRead:
    """Generate the schedule and start the tournament (FR-035).

    A round robin gets all its rounds (BR-050 to BR-052), and the first
    matches take the fields (BR-130). A started tournament is 409
    `tournament_not_in_setup`; a stale `expected_draw_counter` is 409
    `draw_counter_changed`. Another format is 422 `format_not_supported` for
    now. An incomplete setup is 422: `players_without_partner` (Doubles),
    `not_enough_players`, `dyp_halves_incomplete`, `dyp_halves_unequal`,
    `too_many_left_out` (DYP), `not_enough_entries` (FR-032) or
    `too_many_entries_for_round_robin` (detail `limit`: 64).
    """
    tournament = tournament_service.start_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        expected_draw_counter=body.expected_draw_counter,
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


@router.post("/tournaments/{tournament_id}/back-to-setup", responses=_WRITE_ERRORS)
def back_to_setup(
    league_id: UUID,
    tournament_id: UUID,
    body: BackToSetupWrite,  # noqa: ARG001  (only "in_progress" validates)
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentRead:
    """Take a started tournament back to setup until the first result (FR-036).

    A tournament that is not in progress is 409 `tournament_not_in_progress`;
    one with a result is 422 `tournament_has_results`. The schedule goes; the
    entries, seeds and draws stay.
    """
    tournament = tournament_service.back_to_setup(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


@router.put("/tournaments/{tournament_id}/format", responses=_WRITE_ERRORS)
def set_tournament_format(
    league_id: UUID,
    tournament_id: UUID,
    body: TournamentFormatWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Set the format of a tournament in setup (FR-030, FR-031, FR-039).

    A new type keeps the picked players and makes the entries again. A started
    tournament is 409 `tournament_not_in_setup`, as for every setup write.
    """
    setup = tournament_service.set_tournament_format(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        fmt=_format_request(body),
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.get("/tournaments/{tournament_id}/setup")
def read_tournament_setup(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> TournamentSetupRead:
    """Return a tournament's setup; another league's tournament is 404."""
    setup = tournament_service.read_tournament_setup(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return TournamentSetupRead.model_validate(setup)


@router.put("/tournaments/{tournament_id}/setup/players", responses=_WRITE_ERRORS)
def set_tournament_players(
    league_id: UUID,
    tournament_id: UUID,
    body: PlayersWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Pick the tournament's players (FR-032).

    An id that is not a player of the league is 404 `player_not_found`; a
    removed player is 409 `player_removed` (BR-002): reload. A change makes the entries
    and draws again, and increments the draw counter (ADR-010).
    """
    setup = tournament_service.set_tournament_players(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        player_ids=body.player_ids,
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.put("/tournaments/{tournament_id}/setup/pairs", responses=_WRITE_ERRORS)
def set_doubles_pairs(
    league_id: UUID,
    tournament_id: UUID,
    body: PairsWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Set a Doubles tournament's pairs (FR-033, BR-003, BR-030).

    A player who is not picked is 409 `player_not_picked`; a tournament of
    another type is 409 `tournament_type_changed`. Reload on both.
    """
    setup = tournament_service.set_doubles_pairs(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        pairs=body.pairs,
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.put("/tournaments/{tournament_id}/setup/halves", responses=_WRITE_ERRORS)
def set_dyp_halves(
    league_id: UUID,
    tournament_id: UUID,
    body: HalvesWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Make a DYP tournament's halves by ranking or by hand (FR-033, BR-032).

    Once every picked player has a half and the halves are equal, with at most
    one left out, the partners are drawn (BR-033). 409 `player_not_picked` and
    `tournament_type_changed` as for pairs.
    """
    setup = tournament_service.set_dyp_halves(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        method=body.method,
        halves={half.player_id: half.half for half in body.halves},
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.put("/tournaments/{tournament_id}/setup/seeding", responses=_WRITE_ERRORS)
def set_seeding_method(
    league_id: UUID,
    tournament_id: UUID,
    body: SeedingWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Seed by league ranking or by random shuffle (FR-034).

    Monster DYP has no seeds: 409 `tournament_type_changed`.
    """
    setup = tournament_service.set_seeding_method(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        method=body.method,
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.put("/tournaments/{tournament_id}/setup/seed-order", responses=_WRITE_ERRORS)
def set_seed_order(
    league_id: UUID,
    tournament_id: UUID,
    body: SeedOrderWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Reorder the seeds by hand (FR-034).

    An order that does not list exactly the current entries is 409
    `seed_order_changed`: reload.
    """
    setup = tournament_service.set_seed_order(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        entry_ids=body.entry_ids,
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


@router.post("/tournaments/{tournament_id}/setup/draw", responses=_WRITE_ERRORS)
def draw_again(
    league_id: UUID,
    tournament_id: UUID,
    body: DrawWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentSetupRead:
    """Draw again: a new DYP draw, the rest of Doubles paired, or a shuffle (ADR-010).

    A stale `expected_draw_counter` is 409 `draw_counter_changed` with the
    current `draw_counter`. Shuffling seeds that come from the ranking is 409
    `seeding_method_changed`. A DYP draw needs complete, valid halves: 422
    `dyp_halves_incomplete`, `dyp_halves_unequal`, `too_many_left_out` or
    `not_enough_players`. Pairing the rest of Doubles with fewer than two
    unpaired players is 422 `nothing_to_pair`; nothing changes.
    """
    setup = tournament_service.draw_again(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        target=body.target,
        expected_draw_counter=body.expected_draw_counter,
        clock=clock,
    )
    return TournamentSetupRead.model_validate(setup)


def _format_request(body: TournamentFormatWrite | TournamentCreate) -> FormatRequest:
    return FormatRequest(
        name=body.name,
        date=body.date,
        type=body.type,
        group_phase=body.group_phase,
        round_robin_legs=body.round_robin_legs,
        sit_out_points=body.sit_out_points,
        group_match_format=body.group_match_format,
        knockout_match_format=body.knockout_match_format,
        final_match_format=body.final_match_format,
        third_place_match=body.third_place_match,
        goals_per_game=body.goals_per_game,
        field_count=body.field_count,
    )
