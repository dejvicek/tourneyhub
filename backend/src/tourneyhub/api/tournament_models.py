from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    UUID7,
    AfterValidator,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)
from pydantic_core import PydanticCustomError

from tourneyhub.api.schemas import INT_MAX, RequestModel, ResponseModel
from tourneyhub.engine.dyp import DypHalf
from tourneyhub.engine.knockout import RoundName
from tourneyhub.engine.leagues import (
    MAX_FIELD_COUNT,
    MAX_GOALS_PER_GAME,
    MAX_PLAYERS_PER_LEAGUE,
)
from tourneyhub.engine.results import MAX_GAMES
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
    ParticipantState,
    PhaseFormat,
    PhaseKind,
    SeedingMethod,
    Tiebreaker,
    TournamentState,
    TournamentType,
)
from tourneyhub.errors import ErrorCode
from tourneyhub.services.tournaments import DrawTarget

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


class TopPlayersWrite(RequestModel):
    """The players the organizer marks as Monster DYP top players (FR-041, BR-061).

    The target state: a player not listed is not marked. At most one per match
    of round 1 (422 `too_many_top_players`).
    """

    player_ids: PlayerIds


class DisabledWrite(RequestModel):
    """Disable or enable an entry, the target state (FR-044, BR-064, ADR-008)."""

    disabled: bool


class ParticipantRead(ResponseModel):
    """A main entry of a running tournament and where it stands (FR-044, BR-064).

    `state` is `disabled` for a disabled entry, else `sat_out` when it sat out
    the latest group round, else `playing`. The round numbers refer to the group
    phase, also during a knockout. `disabled_since_round` is the first round the
    entry was left out of, or will be: set only while it is disabled.
    `joined_round` is set only for a late player. `sat_out_round` is the latest
    group round, set only when the entry sat it out.
    """

    entry_id: UUID
    state: ParticipantState
    joined_round: int | None
    disabled_since_round: int | None
    sat_out_round: int | None


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


class SwissMatchRead(MatchRead):
    """A match of a Swiss round just drawn, with what a lot decided (ADR-009).

    `is_repeat`: the two have met before, as no draw without a repeat existed
    (BR-057). `is_decided_by_lot`: a lot placed either entry in the standings
    the pair was drawn from (BR-074).
    """

    is_repeat: bool
    is_decided_by_lot: bool


class SwissRoundRead(ResponseModel):
    """A Swiss round just drawn: a `RoundRead` with what a lot decided (ADR-009).

    `is_sit_out_by_lot`: a lot picked the entry that sits out from candidates
    that share its place (BR-058, BR-074). Only the draw returns these marks;
    the tournament read shows the round without them.
    """

    id: UUID
    phase_id: UUID
    round_no: int
    matches: list[SwissMatchRead]
    sitting_out: list[UUID]
    is_sit_out_by_lot: bool


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
    rounds, and `bracket_size` is null. A Swiss lists round 1, drawn from the
    seeds (BR-055, BR-058), and its counts are null: its later rounds are
    drawn one at a time from the standings (FR-040). A knockout without a group phase lists
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
    it is required there, and optional for a match whose sides are stored,
    as in every round of a Lord have mercy knockout. That knockout can answer
    422 `round_locked` (BR-146) once the next round is drawn.
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
    decide or the place is shared. `form` and `ahead_by` are the round
    robin's: a Swiss has an empty `form` and a null `ahead_by`, since its
    tie-breakers are the phase's own, in its order (FR-043, BR-072). `bh1`
    and `bh2` are for Swiss and Monster DYP (BR-073), null in a round robin.
    `game_difference` ranks a round robin, in every match format, a walkover
    counting the games needed to win (BR-101); a Swiss only shows it, since
    its tie-breakers alone order level entries (BR-072). The screen shows
    its column only in BO3 and BO5. `sat_out` counts sit-outs, not rounds missed while disabled
    (FR-060).
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
    (BR-130, BR-132). `standings` are the group phase's, best first: a round
    robin's (BR-101), a Swiss's or a Monster DYP's (BR-072 to BR-074), a
    Monster DYP's one row per player. `group_done` says every group-phase
    match has a result, in a Swiss and a Monster DYP every match of the newest
    round, so the organizer chooses: knockout or finish, or in a Swiss also
    the next round (FR-040).
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


class RoundCreate(RequestModel):
    """The next Swiss round, with the number it expects to get (FR-040, ADR-008).

    `expected_round_no` is the newest round's number plus one, so a repeat
    gets 409 `round_number_changed` instead of a second round.
    """

    expected_round_no: Annotated[int, Field(ge=1, le=INT_MAX)]


class TiebreakersWrite(RequestModel):
    """The enabled tie-breakers of a Swiss or Monster DYP, first one first (FR-043).

    The target state: a tie-breaker left out is switched off, and an empty
    list leaves entries level on points to the lot (BR-074). The default is
    `bh1`, `bh2`, `score_difference`. A tie-breaker named twice is 422
    `validation_failed` (`given_twice`).
    """

    tiebreakers: Annotated[
        list[Tiebreaker], Field(max_length=len(Tiebreaker)), AfterValidator(_distinct)
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
    "replaced",
]


class PlaceReasonRead(ResponseModel):
    """Why an entry has its place (§7.13).

    An entry that did not go through to the knockout, or every entry of a
    group phase without one, has `group_place`: its place in the standings
    and the phase's format (BR-103). A knockout entry has the final, the
    third-place match or `lost_in_round` with the `round` it went out in, the
    `score` of that match (the entry's first: a BO1 game's goals, else the
    games won; null for a walkover or a game without a score) and the
    opponent (BR-102); its `group_place` is that of the entry it continues,
    null for a pair after Monster DYP rounds, which continues no single entry.

    After a Lord have mercy knockout every row is one player's, by their main
    entry (BR-145): `partner_entry_id` is the main entry of the partner of
    the player's last knockout match, null for a player who did not qualify
    and everywhere else; `opponent_entry_id` is null; `group_place` is the
    player's own. A player who was replaced (BR-151) has `replaced`: placed as
    if knocked out in `round`, the round of the seat their replacement gave
    up, with `partner_entry_id` the other player of that pair now and no
    `score`.
    """

    kind: PlaceReasonKind
    round: RoundName | None
    score: tuple[int, int] | None
    opponent_entry_id: UUID | None
    group_place: int | None
    group_format: PhaseFormat | None
    partner_entry_id: UUID | None


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
