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
export type LeagueRead = components["schemas"]["LeagueRead"];

// ---------------------------------------------------------------- shared

export type Language = "en" | "cs";
export type MatchFormat = "bo1" | "bo2" | "bo3" | "bo5";
export type TournamentType = "singles" | "doubles" | "dyp" | "monster_dyp";
export type TournamentState = "setup" | "in_progress" | "finished";
export type Side = "side_1" | "side_2";
export type Outcome = Side | "draw";

// ---------------------------------------------------------------- auth

export interface Me {
  id: Uuid;
  email: string;
  display_name: string;
  language: Language;
  is_admin: boolean;
}

export interface SignUpRequest {
  email: string;
  display_name: string;
  password: string;
  signup_code: string;
}

// ---------------------------------------------------------------- leagues

export interface LeagueSummary {
  id: Uuid;
  name: string;
  active_season: SeasonRead;
  player_count: number;
}

export interface LeagueSettings {
  name: string;
  draws_allowed: boolean;
  default_field_count: number;
  default_match_format: Exclude<MatchFormat, "bo2">;
  default_goals_per_game: number;
  /** The active season's table (DATA-MODEL §4.2). */
  placement_points: number[];
  share_token: string;
}

// ---------------------------------------------------------------- players

export interface Player {
  id: Uuid;
  name: string;
  removed_at: IsoDateTime | null;
}

export interface PlayerCreate {
  name: string;
}

// ---------------------------------------------------------------- seasons and standings

export interface SeasonRead {
  id: Uuid;
  number: number;
  /** Null means the default name, "Season {number}" in the UI language. */
  name: string | null;
  state: "active" | "closed";
  placement_points: number[];
  started_at: IsoDateTime;
  closed_at: IsoDateTime | null;
}

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
   * Swiss or Monster DYP phase is between rounds.
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
  players: Player[];
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
interface NoParams {
  query?: never;
  header?: never;
  path?: never;
  cookie?: never;
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
interface Post<P, B, R> {
  parameters: P;
  requestBody: { content: { "application/json": B } };
  responses: { 201: Json<R> } & Errors;
}

type League = Params<{ league_id: Uuid }>;
type Season = Params<{ league_id: Uuid; season_id: Uuid }>;
type Tournament = Params<{ league_id: Uuid; tournament_id: Uuid }>;
type Match = Params<{ league_id: Uuid; tournament_id: Uuid; match_id: Uuid }>;

/** Routes the demo serves that the generated schema does not have yet. */
export interface ProvisionalPaths {
  // auth
  "/api/v1/me": { get: Get<NoParams, Me> };
  "/api/v1/auth/signup": { post: Post<NoParams, SignUpRequest, Me> };

  // leagues
  "/api/v1/leagues": { get: Get<NoParams, LeagueSummary[]> };
  "/api/v1/leagues/{league_id}/settings": {
    get: Get<League, LeagueSettings>;
    put: Put<League, Omit<LeagueSettings, "share_token">, LeagueSettings>;
  };

  // players
  "/api/v1/leagues/{league_id}/players": {
    get: Get<League, Player[]>;
    post: Post<League, PlayerCreate, Player>;
  };

  // seasons and standings
  "/api/v1/leagues/{league_id}/seasons": { get: Get<League, SeasonRead[]> };
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

export type DemoPaths = MergePaths<GeneratedPaths, ProvisionalPaths>;
