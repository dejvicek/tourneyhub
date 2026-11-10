// The provisional API contract of the demo: request and response types for
// the routes the backend does not have yet, written in the shape that
// openapi-typescript generates, so that openapi-fetch types calls to them.
// It is a stand-in and may change freely. When the backend adds a route, the
// generated src/api/schema.d.ts types it: delete it here, and the screen's
// api.ts switches from provisionalApi to api (src/demo/README.md).
//
// Names follow the API's conventions (ADR-008, DATA-MODEL.md): /api/v1,
// snake_case, UUIDs, enumerations as string literals. Routes are grouped by
// area, like the handlers in src/demo/handlers/.
import type { components, paths as GeneratedPaths } from "@/api/schema";

import type { MonsterKnockoutMode, SwissTiebreaker } from "./rules";

type Uuid = string;
/** A calendar date, YYYY-MM-DD. */
type IsoDate = string;
/** An instant, ISO 8601 in UTC. */
type IsoDateTime = string;

export type ErrorResponse = components["schemas"]["ErrorResponse"];
// Generated types the provisional ones below build on.
export type LeagueRead = components["schemas"]["LeagueRead"];
export type SeasonRead = components["schemas"]["SeasonRead"];
export type UserRead = components["schemas"]["UserRead"];
export type PlayerRead = components["schemas"]["PlayerRead"];

// ---------------------------------------------------------------- shared

export type MatchFormat = "bo1" | "bo2" | "bo3" | "bo5";
export type TournamentType = "singles" | "doubles" | "dyp" | "monster_dyp";
export type TournamentState = "setup" | "in_progress" | "finished";
export type Side = "side_1" | "side_2";
export type Outcome = Side | "draw";

// ---------------------------------------------------------------- seasons and standings

export interface SeasonStandingRow {
  place: number;
  player_id: Uuid;
  points: number;
  tournaments_played: number;
  tournament_wins: number;
}

// ---------------------------------------------------------------- tournaments

export type PhaseKind = "group" | "knockout";
export type GroupFormat = "round_robin" | "swiss" | "monster_dyp";
export type PhaseFormat = GroupFormat | "single_elimination";

/** A phase as the tournament list and the tournament's header need it (DATA-MODEL §4.3). */
export interface PhaseSummary {
  id: Uuid;
  position: number;
  kind: PhaseKind;
  format: PhaseFormat;
}

export interface TournamentSummary {
  id: Uuid;
  season_id: Uuid;
  name: string;
  date: IsoDate;
  type: TournamentType;
  state: TournamentState;
  /** In order: at most one group phase and one knockout (DATA-MODEL §4.3). */
  phases: PhaseSummary[];
  /**
   * Computed on read: the phase being played, the last one with a round
   * drawn; null before the first draw.
   */
  current_phase_id: Uuid | null;
  /**
   * Computed on read: every match of the current phase drawn so far has a
   * result. A round robin's schedule is drawn whole, so it is then done; a
   * Swiss or Monster DYP phase is then between rounds, and its organizer
   * decides on screen 11 whether another round follows.
   */
  current_phase_done: boolean;
}

export interface PhaseRead extends PhaseSummary {
  round_robin_legs: 1 | 2 | null;
  sit_out_points: 0 | 1 | null;
  tiebreakers: SwissTiebreaker[] | null;
  qualifiers: number | null;
  third_place_match: boolean | null;
  monster_knockout_mode: MonsterKnockoutMode | null;
  match_format: MatchFormat;
  final_match_format: Exclude<MatchFormat, "bo2"> | null;
}

export interface EntryRead {
  id: Uuid;
  stage: "main" | "knockout";
  kind: "player" | "pair";
  seed: number | null;
  player_ids: Uuid[];
  is_disabled: boolean;
  is_top_player: boolean;
}

export interface GameRead {
  game_no: number;
  winner: Outcome;
  score_1: number | null;
  score_2: number | null;
}

export interface MatchSideRead {
  entry_id: Uuid | null;
  player_ids: Uuid[];
  is_bye: boolean;
}

export interface MatchRead {
  id: Uuid;
  round_id: Uuid;
  position: number;
  kind: "standard" | "third_place";
  sides: [MatchSideRead, MatchSideRead];
  outcome: Outcome | null;
  is_walkover: boolean;
  games: GameRead[];
  result_entered_at: IsoDateTime | null;
}

export interface RoundRead {
  id: Uuid;
  phase_id: Uuid;
  round_no: number;
  matches: MatchRead[];
  /** Entries that sit this round out (BR-051, BR-058, BR-063). */
  sitting_out: Uuid[];
}

export interface FieldRead {
  id: Uuid;
  number: number;
  match_id: Uuid | null;
}

export interface PlaceRow {
  place: number;
  entry_id: Uuid;
  /** Season points each player of the entry earns (BR-110, BR-111). */
  points_per_player: number;
}

export interface TournamentRead extends TournamentSummary {
  goals_per_game: number;
  phases: PhaseRead[];
  entries: EntryRead[];
  rounds: RoundRead[];
  fields: FieldRead[];
  /** Matches waiting for a field, in the order they will get one (FR-092). */
  waiting: Uuid[];
  /** Set once the tournament is finished (§7.13). */
  places: PlaceRow[] | null;
}

export interface TournamentStandingRow {
  place: number;
  entry_id: Uuid;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  sat_out: number;
  points: number;
  score_difference: number;
}

// ---------------------------------------------------------------- results

export interface GameWrite {
  winner: Outcome;
  score_1: number | null;
  score_2: number | null;
}

/** A whole result, every game or a walkover, never one game (ADR-008). */
export interface ResultWrite {
  walkover_winner: Side | null;
  games: GameWrite[];
}

// ---------------------------------------------------------------- public

export interface PublicLeague {
  name: string;
  seasons: SeasonRead[];
  players: PlayerRead[];
  /** Tournaments of the active season, without those in setup (FR-070). */
  tournaments: TournamentSummary[];
  standings: SeasonStandingRow[];
}

// ---------------------------------------------------------------- paths

interface Json<T> {
  headers: Record<string, unknown>;
  content: { "application/json": T };
}
interface Errors {
  default: Json<ErrorResponse>;
}
interface Params<P> {
  query?: never;
  header?: never;
  path: P;
  cookie?: never;
}
interface Get<P, R> {
  parameters: P;
  requestBody?: never;
  responses: { 200: Json<R> } & Errors;
}
interface Put<P, B, R> {
  parameters: P;
  requestBody: { content: { "application/json": B } };
  responses: { 200: Json<R> } & Errors;
}

type Season = Params<{ league_id: Uuid; season_id: Uuid }>;
type Tournament = Params<{ league_id: Uuid; tournament_id: Uuid }>;
type Match = Params<{ league_id: Uuid; tournament_id: Uuid; match_id: Uuid }>;

/** Routes the demo serves that the generated schema does not have yet. */
export interface ProvisionalPaths {
  // season standings
  "/api/v1/leagues/{league_id}/seasons/{season_id}/standings": {
    get: Get<Season, SeasonStandingRow[]>;
  };

  // tournaments
  "/api/v1/leagues/{league_id}/seasons/{season_id}/tournaments": {
    get: Get<Season, TournamentSummary[]>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}": {
    get: Get<Tournament, TournamentRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/standings": {
    get: Get<Tournament, TournamentStandingRow[]>;
  };

  // results
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/matches/{match_id}/result": {
    put: Put<Match, ResultWrite, MatchRead>;
  };

  // public
  "/api/v1/public/{share_token}": {
    get: Get<Params<{ share_token: string }>, PublicLeague>;
  };
  "/api/v1/public/{share_token}/tournaments/{tournament_id}": {
    get: Get<
      Params<{ share_token: string; tournament_id: Uuid }>,
      TournamentRead
    >;
  };
}

/**
 * The generated paths plus the provisional ones. A path in both keeps its
 * generated methods and gains the provisional ones; a method in both would
 * be a contract error, so delete it here once the backend has it.
 */
type MergePaths<A, B> = {
  [K in keyof A | keyof B]: K extends keyof B
    ? K extends keyof A
      ? Omit<A[K], keyof B[K]> & B[K]
      : B[K]
    : K extends keyof A
      ? A[K]
      : never;
};

/** The HTTP methods a path item defines: openapi-typescript writes `get?: never` for the others. */
type DefinedMethods<T> = {
  [K in keyof T]-?: K extends "parameters"
    ? never
    : [Exclude<T[K], undefined>] extends [never]
      ? never
      : K;
}[keyof T];

/** "path method" for each method that both the contract and the generated schema define. */
type Duplicates = {
  [P in keyof ProvisionalPaths & keyof GeneratedPaths]: `${P} ${DefinedMethods<
    ProvisionalPaths[P]
  > &
    DefinedMethods<GeneratedPaths[P]> &
    string}`;
}[keyof ProvisionalPaths & keyof GeneratedPaths];

/**
 * Fails `pnpm typecheck` once the backend serves a route the contract still
 * declares; the error names it as "path method". Delete it here
 * (src/demo/README.md, "Switching an area to the real API").
 */
type NoDuplicates<T extends never> = T;
export type ContractDuplicates = NoDuplicates<Duplicates>;

export type DemoPaths = MergePaths<
  GeneratedPaths,
  ProvisionalPaths & SetupPaths
>;

// ================================================================ setup
// Tournament list and setup, screens 1-5 (FR-030-FR-039). Modelled on
// DATA-MODEL §4.3-4.4 (tournaments, phases, entries, dyp_halves) and ADR-008:
// a tournament is created with a client id, every write sends the target
// state, and "shuffle again", "new DYP draw" and "generate" carry the
// expected draw counter (409 when it is stale).

export type GroupPhaseChoice = "round_robin" | "swiss" | "monster_dyp" | "none";
export type KnockoutMatchFormat = Exclude<MatchFormat, "bo2">;
export type SeedingMethod = "ranking" | "random";
export type HalvesMethod = "ranking" | "by_hand";
export type Half = "top" | "bottom" | "left_out";

/** Stable 409 codes of setup; a 409 makes the screen reload (ADR-008). */
export type SetupConflictCode =
  | "draw_counter_changed"
  | "seed_order_changed"
  | "tournament_not_in_setup"
  | "tournament_id_taken";

/** Everything screen 2 sets, as a whole (ADR-008: the target state). */
export interface TournamentFormatWrite {
  name: string;
  date: IsoDate;
  type: TournamentType;
  /** Monster DYP always plays "monster_dyp"; the others never do. */
  group_phase: GroupPhaseChoice;
  /** Round robin only. */
  round_robin_legs: 1 | 2;
  /** FR-039, BR-071; unused without a group phase. */
  sit_out_points: 0 | 1;
  /** The group phase's format; "bo2" only in a league that allows draws (BR-121). */
  group_match_format: MatchFormat;
  /** The knockout's format. After a group phase it is applied when the knockout starts. */
  knockout_match_format: KnockoutMatchFormat;
  /** Null: the final plays the knockout's format (BR-120). */
  final_match_format: KnockoutMatchFormat | null;
  /** Only for a knockout without a group phase (FR-031). */
  third_place_match: boolean;
  goals_per_game: number;
  field_count: number;
}

export interface TournamentCreate extends TournamentFormatWrite {
  /** UUIDv7 made by the client; a repeated create returns the same tournament. */
  id: Uuid;
}

export interface DypHalfWrite {
  player_id: Uuid;
  half: Half;
}

/** What setup knows beyond TournamentRead (DATA-MODEL §4.3, §4.4). */
export interface TournamentSetupRead {
  tournament_id: Uuid;
  format: TournamentFormatWrite;
  seeding_method: SeedingMethod;
  /** Incremented by each draw: players changed, "new DYP draw", "shuffle again". */
  draw_counter: number;
  /** The players picked for the tournament, in the league ranking's order. */
  player_ids: Uuid[];
  halves_method: HalvesMethod;
  /** DYP only; a picked player without a row has no half yet. */
  halves: DypHalfWrite[];
  /** Monster DYP: the players the organizer marked as top players (FR-041). */
  top_player_ids: Uuid[];
}

export interface RankingRow {
  rank: number;
  player_id: Uuid;
  /** The current season's points (BR-020). */
  points: number;
}

export interface PreviewMatch {
  /** The players of each side. */
  sides: [Uuid[], Uuid[]];
}

export interface PreviewRound {
  round_no: number;
  matches: PreviewMatch[];
  /** The players of each entry that sits the round out. */
  sitting_out: Uuid[][];
}

/** What "Generate and start" would create (FR-035). */
export interface SchedulePreview {
  /** Round robin: all rounds. Swiss, Monster DYP and a knockout: the first round. */
  rounds: PreviewRound[];
  /** Null when rounds are added one by one. */
  match_count: number | null;
  round_count: number | null;
  /** A knockout's bracket size (BR-040). */
  bracket_size: number | null;
}

interface Delete<P> {
  parameters: P;
  requestBody?: never;
  responses: {
    204: { headers: Record<string, unknown>; content?: never };
  } & Errors;
}
interface Action<P, B, R> {
  parameters: P;
  requestBody: { content: { "application/json": B } };
  responses: { 200: Json<R> } & Errors;
}

/** The routes of tournament list and setup; merged into DemoPaths. */
export interface SetupPaths {
  "/api/v1/leagues/{league_id}/ranking": { get: Get<League, RankingRow[]> };
  "/api/v1/leagues/{league_id}/tournaments": {
    post: Post<League, TournamentCreate, TournamentRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}": {
    delete: Delete<Tournament>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/format": {
    put: Put<Tournament, TournamentFormatWrite, TournamentRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup": {
    get: Get<Tournament, TournamentSetupRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/players": {
    put: Put<Tournament, { player_ids: Uuid[] }, TournamentSetupRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/halves": {
    put: Put<
      Tournament,
      { method: HalvesMethod; halves: DypHalfWrite[] },
      TournamentSetupRead
    >;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/pairs": {
    put: Put<Tournament, { pairs: [Uuid, Uuid][] }, TournamentSetupRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/top-players": {
    put: Put<Tournament, { player_ids: Uuid[] }, TournamentSetupRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/seeding": {
    put: Put<Tournament, { method: SeedingMethod }, TournamentSetupRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/seed-order": {
    put: Put<Tournament, { entry_ids: Uuid[] }, TournamentSetupRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/draw": {
    post: Action<
      Tournament,
      { expected_draw_counter: number; target: "pairs" | "seeds" },
      TournamentSetupRead
    >;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/preview": {
    get: Get<Tournament, SchedulePreview>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/start": {
    post: Action<Tournament, { expected_draw_counter: number }, TournamentRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/back-to-setup": {
    post: Action<
      Tournament,
      { expected_state: TournamentState },
      TournamentRead
    >;
  };
}
