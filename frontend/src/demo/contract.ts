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

export type ErrorResponse = components["schemas"]["ErrorResponse"];
// Generated types the provisional ones below build on.
export type LeagueRead = components["schemas"]["LeagueRead"];
export type SeasonRead = components["schemas"]["SeasonRead"];
export type UserRead = components["schemas"]["UserRead"];
export type PlayerRead = components["schemas"]["PlayerRead"];
export type TournamentSummary = components["schemas"]["TournamentSummary"];
export type PhaseSummary = components["schemas"]["PhaseSummary"];
export type TournamentSetupRead = components["schemas"]["TournamentSetupRead"];

// ---------------------------------------------------------------- shared

export type MatchFormat = "bo1" | "bo2" | "bo3" | "bo5";
export type TournamentType = "singles" | "doubles" | "dyp" | "monster_dyp";
export type TournamentState = "setup" | "in_progress" | "finished";
export type Side = "side_1" | "side_2";
export type Outcome = Side | "draw";

// ---------------------------------------------------------------- demo only

/** Never in the backend: the seeded account the login shows in demo mode. */
export interface DemoAccount {
  email: string;
  password: string;
  signup_code: string;
}

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

// The whole tournament with its rounds and fields (P7b): generated. The
// running screens read it from GET …/tournaments/{tournament_id}.
export type PhaseRead = components["schemas"]["PhaseRead"];
export type EntryRead = components["schemas"]["EntryRead"];
export type GameRead = components["schemas"]["GameRead"];
export type MatchSideRead = components["schemas"]["MatchSideRead"];
export type MatchRead = components["schemas"]["MatchRead"];
export type RoundRead = components["schemas"]["RoundRead"];
export type FieldRead = components["schemas"]["FieldRead"];
export type TournamentRead = components["schemas"]["TournamentRead"];

export interface PlaceRow {
  place: number;
  entry_id: Uuid;
  /** Season points each player of the entry earns (BR-110, BR-111). */
  points_per_player: number;
}

/**
 * The tournament as the share link shows it: the organizer's read plus the
 * places once it is finished (§7.13). The places wait for P10.
 */
export interface PublicTournamentRead extends TournamentRead {
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
// A whole result, every game or a walkover (ADR-008, P8): generated. The
// empty result clears it.

export type GameWrite = components["schemas"]["GameWrite"];
export type ResultWrite = components["schemas"]["ResultWrite"];

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
interface Post<P, B, R> {
  parameters: P;
  requestBody: { content: { "application/json": B } };
  responses: { 201: Json<R> } & Errors;
}
interface Put<P, B, R> {
  parameters: P;
  requestBody: { content: { "application/json": B } };
  responses: { 200: Json<R> } & Errors;
}

type Season = Params<{ league_id: Uuid; season_id: Uuid }>;
type Tournament = Params<{ league_id: Uuid; tournament_id: Uuid }>;

/** Routes the demo serves that the generated schema does not have yet. */
export interface ProvisionalPaths {
  // season standings
  "/api/v1/leagues/{league_id}/seasons/{season_id}/standings": {
    get: Get<Season, SeasonStandingRow[]>;
  };

  // players: the unfinished tournaments a player is in, which block a removal (BR-002)
  "/api/v1/leagues/{league_id}/players/{player_id}/tournaments": {
    get: Get<Params<{ league_id: Uuid; player_id: Uuid }>, TournamentSummary[]>;
  };

  // public
  "/api/v1/public/{share_token}": {
    get: Get<Params<{ share_token: string }>, PublicLeague>;
  };
  "/api/v1/public/{share_token}/tournaments/{tournament_id}": {
    get: Get<
      Params<{ share_token: string; tournament_id: Uuid }>,
      PublicTournamentRead
    >;
  };
  "/api/v1/public/{share_token}/tournaments/{tournament_id}/standings": {
    get: Get<
      Params<{ share_token: string; tournament_id: Uuid }>,
      TournamentStandingRow[]
    >;
  };

  // public: the knockout, the Swiss and Monster DYP ranking and the places
  // (the same reads as the organizer's, without an account)
  "/api/v1/public/{share_token}/tournaments/{tournament_id}/bracket": {
    get: Get<Params<{ share_token: string; tournament_id: Uuid }>, BracketRead>;
  };
  "/api/v1/public/{share_token}/tournaments/{tournament_id}/ranking": {
    get: Get<Params<{ share_token: string; tournament_id: Uuid }>, RankingRead>;
  };
  "/api/v1/public/{share_token}/tournaments/{tournament_id}/places": {
    get: Get<Params<{ share_token: string; tournament_id: Uuid }>, PlacesRead>;
  };

  // demo only: the backend never has this route
  "/api/v1/demo/account": { get: Get<NoParams, DemoAccount> };
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
type Contract = ProvisionalPaths & SetupPaths;
type Duplicates = {
  [P in keyof Contract & keyof GeneratedPaths]: `${P} ${DefinedMethods<
    Contract[P]
  > &
    DefinedMethods<GeneratedPaths[P]> &
    string}`;
}[keyof Contract & keyof GeneratedPaths];

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
// Tournament list and setup, screens 1-5 (FR-030-FR-039). The backend serves
// the list, creating, the format, the picks, the pairs, the halves, the
// seeds, "draw again" and deleting (P7a), and "Generate and start" (FR-035)
// and "Back to setup" (FR-036, P7b), and the schedule preview of the review
// screen; this route waits for a later pull request: the Monster DYP top
// players (FR-041).

// ================================================================ play
// The running group phase, its fields and its end (screens 6–8, FR-040,
// FR-060, FR-090–FR-094). Owned by the play screens; other areas append
// their own sections. These declarations merge into ProvisionalPaths above.

// The play read, finishing and the places (P8): generated. The play read's
// standings serve every format's Standings tab (FR-060).
export type WaitingMatchRead = components["schemas"]["WaitingMatchRead"];
export type PlayStandingRow = components["schemas"]["PlayStandingRow"];
export type FormResult = PlayStandingRow["form"][number];
export type PlayRead = components["schemas"]["PlayRead"];
export type FinishWrite = components["schemas"]["FinishWrite"];

/**
 * Field placements as target states (ADR-008, DATA-MODEL §4.6): a match on
 * a field, or waiting (`field_id: null`). A swap names both matches.
 */
export interface PlacementWrite {
  placements: { match_id: Uuid; field_id: Uuid | null }[];
}

/** A new field carries the number it expects to get, the lowest free one (BR-132). */
export interface FieldCreate {
  number: number;
}

// ================================================================ finals
// Screens 9–13 and the season standings tab: knockout bracket, places,
// Swiss and Monster DYP rounds, late and disabled players, and starting the
// knockout. Served by handlers/finals.ts and handlers/standings.ts.

export type KnockoutMatchState =
  /** A first-round match against an empty spot; the entry goes through (BR-041). */
  | "bye"
  | "played"
  | "on_field"
  /** Both sides are known and no field is assigned. */
  | "ready"
  /** At least one side depends on an earlier match. */
  | "waiting";

/** The last round holds the final and, if played, the third-place match. */
export type BracketRoundName =
  "round_of_16" | "quarterfinal" | "semifinal" | "final";

export interface BracketSide {
  entry_id: Uuid | null;
  seed: number | null;
  is_bye: boolean;
}

export interface BracketMatch {
  match_id: Uuid;
  /** The match number in the tournament, continuing after the group phase; null for a bye. */
  number: number | null;
  round_no: number;
  position: number;
  kind: MatchRead["kind"];
  state: KnockoutMatchState;
  sides: [BracketSide, BracketSide];
  outcome: Outcome | null;
  is_walkover: boolean;
  /** Goals of a BO1 game, otherwise the games won; null before a result. */
  score: [number, number] | null;
  match_format: MatchFormat;
  field_number: number | null;
  /** The number of the match the winner plays in. */
  next_number: number | null;
  /** A later match this one feeds has a result, so this one can't change (BR-094). */
  result_locked: boolean;
}

export interface BracketRound {
  round_no: number;
  name: BracketRoundName;
  matches: BracketMatch[];
}

export interface BracketRead {
  phase_id: Uuid;
  /** 4, 8 or 16, the smallest power of two that fits the entries (BR-040). */
  size: number;
  third_place_match: boolean;
  has_group_phase: boolean;
  rounds: BracketRound[];
}

// The places (P8 for a round robin without a knockout): generated.
export type PlaceReason = components["schemas"]["PlaceReasonRead"];
export type PlaceDetail = components["schemas"]["PlaceRead"];
export type PlacesRead = components["schemas"]["PlacesRead"];

/** One player's change in the season standings after a tournament (screen 10). */
export interface SeasonEffectRow {
  player_id: Uuid;
  place: number;
  points: number;
  /** Placement points earned in this tournament. */
  earned: number;
  /** The place before this tournament; null if the player had none. */
  previous_place: number | null;
}

export interface SwissRankingRow {
  place: number;
  entry_id: Uuid;
  played: number;
  sat_out: number;
  points: number;
  bh1: number;
  bh2: number;
  score_difference: number;
  is_disabled: boolean;
}

/** Swiss and Monster DYP standings with the tie-breakers (FR-043, BR-072, BR-073). */
export interface RankingRead {
  /** The enabled tie-breakers, in order. */
  tiebreakers: SwissTiebreaker[];
  /** How many go through to the knockout, if the setup said. */
  qualifiers: number | null;
  rows: SwissRankingRow[];
}

export interface ParticipantRead {
  entry_id: Uuid;
  state: "playing" | "sat_out" | "disabled";
  /** The round a late player joined in; null for everyone from round 1. */
  joined_round: number | null;
  /** The round a disabled player was disabled in. */
  disabled_since_round: number | null;
  /** The newest round the entry sat out, if it sat out the latest round. */
  sat_out_round: number | null;
}

export interface RoundAddWrite {
  /** The number the organizer expects the new round to get (ADR-008). */
  expected_round_no: number;
}

export interface DisabledWrite {
  disabled: boolean;
}

export interface LateEntryWrite {
  player_id: Uuid;
  /** The round the player is expected to start in. */
  from_round_no: number;
}

export interface TiebreakersWrite {
  tiebreakers: SwissTiebreaker[];
}

export interface FinishStateWrite {
  state: "finished";
}

export interface KnockoutWrite {
  qualifiers: number;
  third_place_match: boolean;
  /** Null after a round robin or Swiss: the entries play as they are (BR-085). */
  mode: MonsterKnockoutMode | null;
  /** The draw counter: another number draws another lot (ADR-008). */
  draw: number;
}

export interface KnockoutPreviewEntry {
  seed: number;
  /** The standings entries (players) that form it, with their standings places. */
  members: { entry_id: Uuid; place: number }[];
}

export interface KnockoutPreview {
  /** Entries that can go through: the active ones. */
  max_qualifiers: number;
  qualifiers: number;
  entries: KnockoutPreviewEntry[];
  /** The first round by seeds; null is a bye. */
  first_round: [number, number | null][];
  bracket_size: number;
  /** The newest group-phase round, which the draw locks (BR-065). */
  locks_round_no: number;
  /** Standings places of disabled entries who would otherwise have qualified. */
  skipped_entry_ids: Uuid[];
}

interface Delete<P> {
  parameters: P;
  requestBody?: never;
  responses: {
    204: { headers: Record<string, unknown>; content?: never };
  } & Errors;
}

/** The routes of setup the backend does not serve yet; merged into DemoPaths. */
export interface SetupPaths {
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/top-players": {
    put: Put<Tournament, { player_ids: Uuid[] }, TournamentSetupRead>;
  };
}

type PlayField = Params<{
  league_id: Uuid;
  tournament_id: Uuid;
  field_id: Uuid;
}>;

// The results, the play read, finishing and the places are generated (P8).
// Fields wait for P9.
export interface ProvisionalPaths {
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/placements": {
    put: Put<Tournament, PlacementWrite, TournamentRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/fields": {
    post: Post<Tournament, FieldCreate, FieldRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/fields/{field_id}": {
    delete: Delete<PlayField>;
  };
}

type TournamentEntry = Params<{
  league_id: Uuid;
  tournament_id: Uuid;
  entry_id: Uuid;
}>;
type TournamentRound = Params<{
  league_id: Uuid;
  tournament_id: Uuid;
  round_id: Uuid;
}>;
type TournamentPhase = Params<{
  league_id: Uuid;
  tournament_id: Uuid;
  phase_id: Uuid;
}>;

export interface KnockoutPreviewParams {
  path: { league_id: Uuid; tournament_id: Uuid };
  query: {
    qualifiers: number;
    third_place_match: boolean;
    mode?: MonsterKnockoutMode;
    draw: number;
  };
}

// Reopening the interface adds the finals routes to the provisional paths.
export interface ProvisionalPaths {
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/bracket": {
    get: Get<Tournament, BracketRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/season-effect": {
    get: Get<Tournament, SeasonEffectRow[]>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/ranking": {
    get: Get<Tournament, RankingRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/participants": {
    get: Get<Tournament, ParticipantRead[]>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/rounds": {
    post: Post<Tournament, RoundAddWrite, RoundRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/rounds/{round_id}": {
    delete: Delete<TournamentRound>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/entries": {
    post: Post<Tournament, LateEntryWrite, ParticipantRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/entries/{entry_id}/disabled": {
    put: Put<TournamentEntry, DisabledWrite, ParticipantRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/tiebreakers": {
    put: Put<Tournament, TiebreakersWrite, RankingRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/state": {
    put: Put<Tournament, FinishStateWrite, TournamentRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout/preview": {
    get: {
      parameters: KnockoutPreviewParams & {
        header?: never;
        cookie?: never;
      };
      requestBody?: never;
      responses: { 200: Json<KnockoutPreview> } & Errors;
    };
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout": {
    put: Put<Tournament, KnockoutWrite, BracketRead>;
  };
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/phases/{phase_id}": {
    delete: Delete<TournamentPhase>;
  };
}
