from dataclasses import asdict
from datetime import date, datetime
from http import HTTPStatus
from typing import Annotated, Literal, Self
from uuid import UUID

from fastapi import APIRouter
from pydantic import (
    UUID7,
    AfterValidator,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)
from pydantic_core import PydanticCustomError

from tourneyhub.api.deps import ClockDep, CurrentUserDep, SessionDep
from tourneyhub.api.schemas import INT_MAX, ErrorResponse, RequestModel, ResponseModel
from tourneyhub.engine.dyp import DypHalf
from tourneyhub.engine.knockout import RoundName
from tourneyhub.engine.leagues import (
    MAX_FIELD_COUNT,
    MAX_GOALS_PER_GAME,
    MAX_PLAYERS_PER_LEAGUE,
)
from tourneyhub.engine.results import MAX_GAMES, Game
from tourneyhub.engine.standings import FormResult, RoundRobinTiebreaker
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
from tourneyhub.errors import ErrorCode
from tourneyhub.services import tournaments as tournament_service
from tourneyhub.services.tournaments import (
    DrawTarget,
    FieldPlacement,
    FormatRequest,
    MatchResult,
    PlacesView,
)

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

type SitOutPoints = Literal[0, 1, 2]
"""The points for sitting out in Swiss and Monster DYP (FR-039, BR-071)."""

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
        may be null: the final plays the knockout's format; `sit_out_points` may
        be null: the default, 0, FR-039). A round robin has no `sit_out_points`
        (BR-071); the service refuses a number there with its own code.
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
            if (
                complete
                and name in applies - {"final_match_format", "sit_out_points"}
                and value is None
            ):
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

    `sit_out_points` is for a Swiss or Monster DYP group phase (FR-039, BR-071):
    0, 1 or 2 is stored as given (BR-075), and null stores the default, 0. A
    round robin has none: a number there is 422 `sit_out_points_not_applicable`.
    """

    round_robin_legs: Literal[1, 2] | None
    sit_out_points: SitOutPoints | None
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
    round robin leg, 0 points for sitting out in Swiss and Monster DYP (FR-039)
    and no third-place match. A round robin has no points for sitting out
    (BR-071): a number there is 422 `sit_out_points_not_applicable`.
    """

    id: UUID7
    round_robin_legs: Literal[1, 2] | None = None
    sit_out_points: SitOutPoints | None = None
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
    """The format as stored; settings that do not apply are null (FR-031).

    `sit_out_points` is null for a round robin and without a group phase (BR-071).
    """

    name: str
    date: date
    type: TournamentType
    group_phase: GroupPhase
    round_robin_legs: Literal[1, 2] | None
    sit_out_points: SitOutPoints | None
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
    sit_out_points: SitOutPoints | None
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


class StartProblemRead(ResponseModel):
    """The refusal "Generate and start" would answer: the 422's code and detail."""

    code: ErrorCode
    detail: dict[str, JsonValue]


class PreviewMatchRead(ResponseModel):
    """A match of the preview: the players of each side, a pair in entry order."""

    sides: tuple[list[UUID], list[UUID]]


class PreviewRoundRead(ResponseModel):
    """A round of the preview, with the players of each entry that sits it out.

    `byes` lists, by seed, the players of each entry that goes straight to a
    knockout's second round (BR-041); empty in a round robin.
    """

    round_no: int
    matches: list[PreviewMatchRead]
    sitting_out: list[list[UUID]]
    byes: list[list[UUID]]


class SchedulePreviewRead(ResponseModel):
    """What "Generate and start" would create, or why it would not (FR-035).

    `can_start` is false exactly when `problem` is set: the same code and detail
    as the 422 of `POST /start` (the 409s of a stale draw counter apart). Then
    `rounds` is empty and the counts are null. A round robin lists all its
    rounds, and `bracket_size` is null. A knockout without a group phase lists
    its first round with its matches and byes (BR-040 to BR-042);
    `match_count` counts every match of the bracket, the third-place match
    too and no bye, `round_count` its rounds and `bracket_size` its
    first-round spots. `draw_counter` and `seed_order` go back in the start
    (ADR-008): `seed_order` is the entries the preview was drawn from, seed 1
    first, empty with a `problem`.
    """

    draw_counter: int
    seed_order: list[UUID]
    can_start: bool
    problem: StartProblemRead | None
    rounds: list[PreviewRoundRead]
    match_count: int | None
    round_count: int | None
    bracket_size: int | None


class StartWrite(RequestModel):
    """Generate and start, from the setup the review screen showed (ADR-008).

    The draw counter does not change when the organizer reorders the seeds by
    hand, so the request also carries the seed order the preview showed.
    """

    expected_draw_counter: Annotated[int, Field(ge=0, le=INT_MAX)]
    expected_seed_order: EntryIds


class BackToSetupWrite(RequestModel):
    """Back to setup, from the state the screen showed (FR-036, ADR-008)."""

    expected_state: Literal["in_progress"]


class GameWrite(RequestModel):
    """One game: its winner and both scores, or neither (FR-050, FR-051, BR-092).

    Goals per game is a guide, not a rule: any whole number is a score (BR-123).
    """

    winner: Outcome
    score_1: Annotated[int, Field(ge=0, le=INT_MAX)] | None
    score_2: Annotated[int, Field(ge=0, le=INT_MAX)] | None


class ResultWrite(RequestModel):
    """A whole result, the target state (ADR-008): every game played, or a walkover.

    A walkover names its winner and has no games (FR-052, BR-124). No walkover
    and no games is the empty result, which clears the match's result (FR-053).

    `expected_sides` are the entries the screen saw on side 1 and side 2. The
    sides of a knockout match after the first round are derived from the
    winners (DATA-MODEL D4), so "side 1 wins" must name the entry it meant:
    it is required there, and optional for a match whose sides are stored.
    """

    walkover_winner: Literal[Outcome.SIDE_1, Outcome.SIDE_2] | None
    games: Annotated[list[GameWrite], Field(max_length=MAX_GAMES)]
    expected_sides: tuple[UUID, UUID] | None = None

    @model_validator(mode="after")
    def _walkover_has_no_games(self) -> Self:
        if self.walkover_winner is not None and self.games:
            raise PydanticCustomError("walkover_with_games", "a walkover has no games")
        return self


class BusyFieldRead(ResponseModel):
    """A field holding players of a waiting match: why it waits (BR-131)."""

    field_id: UUID
    player_ids: list[UUID]


class WaitingMatchRead(ResponseModel):
    """A match waiting for a field, in the order it will get one (FR-092)."""

    match_id: UUID
    busy: list[BusyFieldRead]


class PlayStandingRow(ResponseModel):
    """One entry's line in the group-phase standings (BR-101, FR-060).

    `place` is shared by entries still level (BR-074), and the next place
    skips (BR-104). In Swiss and Monster DYP, `points` include the sit-out
    points of every round sat out, as soon as the round is drawn (BR-076); a
    round robin gives none (BR-071). `form` lists the latest five
    results, oldest first. `ahead_by` names what ranks the entry above the
    next one when both have the same points, and is null when the points
    decide or the place is shared. `bh1` and `bh2` are for Swiss and Monster
    DYP, null in a round robin. `game_difference` ranks in every match format,
    a walkover counting the games needed to win; the screen shows its column
    only in BO3 and BO5 (BR-101).
    """

    place: int
    entry_id: UUID
    played: int
    won: int
    drawn: int
    lost: int
    sat_out: int
    points: int
    game_difference: int
    score_difference: int
    form: list[FormResult]
    ahead_by: RoundRobinTiebreaker | None
    bh1: int | None
    bh2: int | None


class PlayRead(ResponseModel):
    """The running group phase, computed on read (ADR-009, FR-060, FR-092).

    `waiting` is the waiting list: requeued matches first, then schedule order
    (BR-130, BR-132). `standings` are the round robin's, best first; other
    group formats have none yet. `group_done` says every group-phase match has
    a result, so the organizer chooses: knockout or finish (FR-040).
    """

    waiting: list[WaitingMatchRead]
    standings: list[PlayStandingRow]
    group_done: bool


class FieldCreate(RequestModel):
    """A new field, with the number it expects to get: the lowest free one (BR-132).

    The number is the expectation of ADR-008, so a repeat gets 409 instead of
    a second field.
    """

    number: Annotated[int, Field(ge=1, le=MAX_FIELD_COUNT)]


class PlacementWrite(RequestModel):
    """A match on a field, or back to waiting when `field_id` is null (FR-093).

    `from_field_id` is the field the screen saw the match on, null when it
    saw it waiting. A match that is elsewhere now is 409 `placement_changed`.
    """

    match_id: UUID
    field_id: UUID | None
    from_field_id: UUID | None


def _distinct_placements(placements: list[PlacementWrite]) -> list[PlacementWrite]:
    _distinct([placement.match_id for placement in placements])
    _distinct([p.field_id for p in placements if p.field_id is not None])
    return placements


class PlacementsWrite(RequestModel):
    """Where matches are to be played, the target state (FR-093, ADR-008).

    One placement puts a waiting match on a free field, moves a match to a
    free field, or sends it back to waiting. A swap is two placements: both
    matches, on fields, with each other's field. Nothing else is allowed
    (422 `placement_not_allowed`). A match or a field named twice is 422
    `validation_failed` (`given_twice`).
    """

    placements: Annotated[
        list[PlacementWrite],
        Field(min_length=1, max_length=2),
        AfterValidator(_distinct_placements),
    ]


class FinishWrite(RequestModel):
    """Finish the tournament, from the state the screen showed (FR-040, ADR-008)."""

    expected_state: Literal["in_progress"]


type PlaceReasonKind = Literal[
    "won_final",
    "lost_final",
    "won_third_place",
    "lost_third_place",
    "lost_in_round",
    "group_place",
]


class PlaceReasonRead(ResponseModel):
    """Why an entry has its place (§7.13).

    An entry that did not go through to the knockout, or every entry of a
    group phase without one, has `group_place`: its place in the standings
    and the phase's format (BR-103). A knockout entry has the final, the
    third-place match or `lost_in_round` with the `round` it went out in, the
    `score` of that match (the entry's first: a BO1 game's goals, else the
    games won; null for a walkover or a game without a score) and the
    opponent (BR-102); its `group_place` is that of the entry it continues.
    """

    kind: PlaceReasonKind
    round: RoundName | None
    score: tuple[int, int] | None
    opponent_entry_id: UUID | None
    group_place: int | None
    group_format: PhaseFormat | None


class PlaceRead(ResponseModel):
    """An entry's final place and the season points each of its players earns.

    Entries sharing a place get the average of the places they cover,
    rounded down; places beyond the season's table earn 0 (BR-110, BR-111).
    """

    place: int
    entry_id: UUID
    points_per_player: int
    reason: PlaceReasonRead


class PlacesRead(ResponseModel):
    """The places of a tournament (§7.13, §7.14), computed on read (D1).

    `complete` is true once the tournament is finished; before that `rows` is
    empty. Rows come best place first.
    """

    complete: bool
    rows: list[PlaceRead]


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
    league without draws is 422 `draws_not_allowed` (BR-121). Points for sitting
    out in a round robin are 422 `sit_out_points_not_applicable` (BR-071).
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

    A round robin gets all its rounds (BR-050 to BR-052); a knockout without
    a group phase gets its whole bracket from the setup seeds, the byes for
    the top seeds (BR-040 to BR-044). The first matches take the fields
    (BR-130). A started tournament is 409 `tournament_not_in_setup`; a stale
    `expected_draw_counter` is 409 `draw_counter_changed`, and an
    `expected_seed_order` that is not the entries' current order, seed 1
    first, 409 `seed_order_changed`: the review shows the new setup. Swiss and
    Monster DYP are 422 `format_not_supported` for now. An incomplete setup is 422:
    `players_without_partner` (Doubles), `not_enough_players`,
    `dyp_halves_incomplete`, `dyp_halves_unequal`, `too_many_left_out` (DYP),
    `not_enough_entries` (FR-032: 2, or 4 with a third-place match),
    `too_many_entries_for_round_robin` (detail `limit`: 64) or
    `too_many_entries_for_knockout` (detail `limit`: 256).
    """
    tournament = tournament_service.start_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        expected_draw_counter=body.expected_draw_counter,
        expected_seed_order=body.expected_seed_order,
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


# The summary below is API text (openapi.json) and was left as it is: "until the
# first result". FR-036 and BR-096 say "while no match in the tournament has a
# result", which is also true again once every result is cleared (FR-053). The
# service already refuses on any result, so only the text changes, in the #48
# follow-up (issue to open after approval).
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
    tournament is 409 `tournament_not_in_setup`, as for every setup write, so the
    points for sitting out cannot change while the phase has a result (BR-075).
    Points for sitting out in a round robin are 422
    `sit_out_points_not_applicable` (BR-071); BO2 in a league without draws, 422
    `draws_not_allowed` (BR-121).
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


@router.get("/tournaments/{tournament_id}/setup/preview")
def read_schedule_preview(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> SchedulePreviewRead:
    """Return what "Generate and start" would create, and write nothing (FR-035).

    A tournament that cannot start is still 200 with `can_start` false and the
    `problem`: `players_without_partner`, `not_enough_entries`,
    `too_many_entries_for_round_robin` (detail `limit`: 64),
    `too_many_entries_for_knockout` (detail `limit`: 256),
    `format_not_supported`, the DYP codes of a draw that cannot be made, or
    `tournament_not_in_setup` for a started tournament. Another league's
    tournament is 404.
    """
    preview = tournament_service.preview_schedule(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return SchedulePreviewRead.model_validate(preview)


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


@router.put(
    "/tournaments/{tournament_id}/matches/{match_id}/result", responses=_WRITE_ERRORS
)
def set_match_result(
    league_id: UUID,
    tournament_id: UUID,
    match_id: UUID,
    body: ResultWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> MatchRead:
    """Enter, replace or clear a match's result (FR-050 to FR-053, FR-094).

    The body is the whole result, so a repeat changes nothing (ADR-008).
    Entering one frees the match's field, which takes the next waiting match
    (BR-130, BR-131). The empty result clears it: the match waits again, not
    put back on its old field (BR-134), and a finished tournament is back in
    progress (BR-095). The free fields are then filled, so the first match that
    can be played takes one, the cleared match included.

    A closed season is 409 `season_closed`. An unknown match is 404
    `match_not_found`. A match whose sides are not both known is 422
    `match_sides_unknown` (BR-091). A result that breaks a rule is 422:
    `result_does_not_fit_format` (BR-121, detail `format` and `games`),
    `draws_not_allowed` (BR-090), `game_score_mismatch` (BR-092, detail
    `game_no`) or `scores_required` (Swiss and Monster DYP, detail `game_no`).
    A walkover with games is 422 `validation_failed`.

    A knockout match after the first round has derived sides: the body names
    the entries the screen saw in `expected_sides`. Other entries, or a side
    still to come, are 409 `match_sides_changed` (detail `entry_ids`, the
    current ones); none is 422 `expected_sides_required`.

    The knockout: once it is drawn, a group-phase result is 422
    `group_phase_locked` (BR-053, detail `phase_id`); a knockout result that a
    later match it feeds has a result for is 422 `result_locked` (BR-094,
    detail `match_ids`), and a knockout has no draws (BR-090). A new winner
    changes the later matches' sides. The result that completes the
    knockout finishes the tournament (FR-037).
    """
    match = tournament_service.set_match_result(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        match_id=match_id,
        user_id=user.id,
        result=MatchResult(
            expected_sides=body.expected_sides,
            walkover_winner=body.walkover_winner,
            games=tuple(
                Game(winner=game.winner, score_1=game.score_1, score_2=game.score_2)
                for game in body.games
            ),
        ),
        clock=clock,
    )
    return MatchRead.model_validate(match)


@router.get("/tournaments/{tournament_id}/play")
def read_play(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> PlayRead:
    """Return the waiting list, the live standings and whether the group phase is done.

    Computed on read (FR-040, FR-060, FR-092). Another league's tournament is
    404 `tournament_not_found`.
    """
    play = tournament_service.read_play(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return PlayRead(
        waiting=[WaitingMatchRead.model_validate(match) for match in play.waiting],
        standings=[
            PlayStandingRow.model_validate(asdict(row) | {"bh1": None, "bh2": None})
            for row in play.standings
        ],
        group_done=play.group_done,
    )


@router.post(
    "/tournaments/{tournament_id}/fields",
    status_code=HTTPStatus.CREATED,
    responses=_WRITE_ERRORS,
)
def add_field(
    league_id: UUID,
    tournament_id: UUID,
    body: FieldCreate,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> FieldRead:
    """Add a field while the tournament runs (FR-090, BR-132).

    The body carries the number the field expects to get, the lowest free
    one. The new field takes the next waiting match at once; `match_id` is
    null when no waiting match can be played.

    A tournament in setup or finished is 409 `tournament_not_in_progress`
    (detail `state`); setup sets the number of fields with the format. Any
    other number, a repeat included, is 409 `field_number_changed` with the
    `number` a new field would get now, null when all 32 are taken.
    """
    field = tournament_service.add_field(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        number=body.number,
        clock=clock,
    )
    return FieldRead.model_validate(field)


@router.delete(
    "/tournaments/{tournament_id}/fields/{field_id}",
    status_code=HTTPStatus.NO_CONTENT,
    responses=_WRITE_ERRORS,
)
def remove_field(
    league_id: UUID,
    tournament_id: UUID,
    field_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> None:
    """Remove a field while the tournament runs; the UI asks first (FR-090, BR-132).

    The other fields keep their numbers. The match on the removed field goes
    to the front of the waiting list, so it takes the next field that frees
    up, or a free one at once.

    An unknown field, or a repeated delete, is 404 `field_not_found`: the
    field is gone. A tournament not in progress is 409
    `tournament_not_in_progress`. The last field is 422 `last_field`.
    """
    tournament_service.remove_field(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        field_id=field_id,
        user_id=user.id,
        clock=clock,
    )


@router.put("/tournaments/{tournament_id}/fields/placements", responses=_WRITE_ERRORS)
def place_matches(
    league_id: UUID,
    tournament_id: UUID,
    body: PlacementsWrite,
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentRead:
    """Place, move, swap or take off matches by hand (FR-093, BR-133).

    Each named match ends on its named field, or waiting, from the field the
    screen saw it on (`from_field_id`). A placement by hand holds until the
    match has a result. A field a match leaves takes the next waiting match,
    but not one this request sends back to waiting, which waits in schedule
    order. Returns the whole
    tournament with its fields and waiting list.

    An unknown match is 404 `match_not_found`, an unknown field 404
    `field_not_found`. A stale screen gets 409: `tournament_not_in_progress`,
    `match_has_result` (detail `match_id`), `placement_changed` (a match is not
    on the `from_field_id` any more) or `field_not_free` (another match is on
    the field now; detail `field_id`, `match_id`). A match whose sides are not
    both known, or with a bye, is 422 `match_sides_unknown` (BR-091). Anything
    but the four operations of FR-093 (replacing the match on a field, a
    rotation) is 422 `placement_not_allowed`.
    A player who would be on two fields at once is 422
    `player_on_another_field` (BR-131; detail `player_ids`, and `field_ids`,
    the fields that would hold them, lowest number first).
    """
    tournament = tournament_service.place_matches(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        placements=[
            FieldPlacement(
                match_id=p.match_id,
                field_id=p.field_id,
                from_field_id=p.from_field_id,
            )
            for p in body.placements
        ],
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


@router.post("/tournaments/{tournament_id}/finish", responses=_WRITE_ERRORS)
def finish_tournament(
    league_id: UUID,
    tournament_id: UUID,
    body: FinishWrite,  # noqa: ARG001  (only "in_progress" validates)
    session: SessionDep,
    user: CurrentUserDep,
    clock: ClockDep,
) -> TournamentRead:
    """Finish a round robin without a knockout, once the UI has asked (FR-040).

    A tournament that is not in progress is 409 `tournament_not_in_progress`
    (detail `state`), so a repeat changes nothing. A match without a result is
    422 `group_phase_not_done` (detail `matches_left`). A tournament with a
    knockout, which finishes with its last result (FR-037), a Swiss or a
    Monster DYP is 422 `format_not_supported`.
    The standings become the places (`GET …/places`).
    """
    tournament = tournament_service.finish_tournament(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=user.id,
        clock=clock,
    )
    return TournamentRead.model_validate(tournament)


@router.get(
    "/tournaments/{tournament_id}/places",
    responses={HTTPStatus.UNPROCESSABLE_CONTENT: {"model": ErrorResponse}},
)
def read_places(
    league_id: UUID, tournament_id: UUID, session: SessionDep, user: CurrentUserDep
) -> PlacesRead:
    """Return the places and the season points of a finished tournament (§7.13, §7.14).

    Computed on read. Before the tournament finishes, `complete` is false and
    there are no rows. With a knockout, its entries take the top places and
    the others follow in their group-phase order (BR-102, BR-103); without a
    group phase, every entry is placed by the knockout, and its reason has no
    `group_place` and no `group_format`. A Swiss or
    a Monster DYP is 422 `format_not_supported` until they are played.
    """
    places = tournament_service.read_places(
        session, league_id=league_id, tournament_id=tournament_id, user_id=user.id
    )
    return places_read(places)


def places_read(places: PlacesView) -> PlacesRead:
    """The places as the API answers them; the organizer's and the viewers' alike."""
    return PlacesRead(
        complete=places.complete,
        rows=[
            PlaceRead(
                place=row.place,
                entry_id=row.entry_id,
                points_per_player=row.points_per_player,
                reason=PlaceReasonRead(
                    kind=row.kind,
                    round=row.round,
                    score=row.score,
                    opponent_entry_id=row.opponent_entry_id,
                    group_place=row.group_place,
                    group_format=places.group_format,
                ),
            )
            for row in places.rows
        ],
    )


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
