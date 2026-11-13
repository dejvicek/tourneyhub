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
import type {
  DisabledWrite,
  LateEntryWrite,
  ParticipantRead,
  RankingRead,
  RoundAddWrite,
  TiebreakersWrite,
} from "@/api/provisionalTypes";
import type { components, paths as GeneratedPaths } from "@/api/schema";

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

// The season standings and a tournament's effect on them (P10a): generated.
export type SeasonStandingRow = components["schemas"]["SeasonStandingRead"];
export type SeasonEffectRow = components["schemas"]["SeasonEffectRead"];

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

/** A round robin's standings as the share link answers them (P10a): generated. */
export type TournamentStandingRow = components["schemas"]["PublicStandingRow"];

// ---------------------------------------------------------------- results
// A whole result, every game or a walkover (ADR-008, P8): generated. The
// empty result clears it.

export type GameWrite = components["schemas"]["GameWrite"];
export type ResultWrite = components["schemas"]["ResultWrite"];

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

type Tournament = Params<{ league_id: Uuid; tournament_id: Uuid }>;

/** Routes the demo serves that the generated schema does not have yet. */
export interface ProvisionalPaths {
  // players: the unfinished tournaments a player is in, which block a removal (BR-002)
  "/api/v1/leagues/{league_id}/players/{player_id}/tournaments": {
    get: Get<Params<{ league_id: Uuid; player_id: Uuid }>, TournamentSummary[]>;
  };

  // public: the league, a season's tournaments, a tournament, the season
  // standings, a round robin's standings, the places and the bracket are
  // generated (P11, P10a, P10b); the Swiss and Monster DYP ranking waits for
  // P12 (the same read as the organizer's, without an account)
  "/api/v1/public/{share_token}/tournaments/{tournament_id}/ranking": {
    get: Get<Params<{ share_token: string; tournament_id: Uuid }>, RankingRead>;
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
// FR-060, FR-090–FR-094): all generated now. Owned by the play screens;
// other areas append their own sections, which merge into ProvisionalPaths
// above.

// The play read, finishing and the places (P8): generated. The play read's
// standings serve every format's Standings tab (FR-060).
export type WaitingMatchRead = components["schemas"]["WaitingMatchRead"];
export type PlayStandingRow = components["schemas"]["PlayStandingRow"];
export type FormResult = PlayStandingRow["form"][number];
export type PlayRead = components["schemas"]["PlayRead"];
export type FinishWrite = components["schemas"]["FinishWrite"];

// Fields (P9): generated. Placements are target states (ADR-008,
// DATA-MODEL §4.6): a match on a field, or waiting (`field_id: null`); a swap
// names both matches. A new field carries the number it expects to get.
export type PlacementsWrite = components["schemas"]["PlacementsWrite"];
export type FieldCreate = components["schemas"]["FieldCreate"];

// ================================================================ finals
// Screens 9–13 and the season standings tab: knockout bracket, places,
// Swiss and Monster DYP rounds, late and disabled players, and starting the
// knockout. Served by handlers/finals.ts and handlers/standings.ts.

// The knockout (P10b): generated. Starting it carries the phase the screen
// saw as current (ADR-008); its preview and the bracket are reads.
export type BracketRoundName = components["schemas"]["RoundName"];
export type BracketSide = components["schemas"]["BracketSideRead"];
export type BracketMatch = components["schemas"]["BracketMatchRead"];
export type KnockoutMatchState = BracketMatch["state"];
export type BracketRound = components["schemas"]["BracketRoundRead"];
export type BracketRead = components["schemas"]["BracketRead"];
export type KnockoutWrite = components["schemas"]["KnockoutWrite"];
export type KnockoutPreview = components["schemas"]["KnockoutPreviewRead"];

// The places (P8 for a round robin without a knockout): generated.
export type PlaceReason = components["schemas"]["PlaceReasonRead"];
export type PlaceDetail = components["schemas"]["PlaceRead"];
export type PlacesRead = components["schemas"]["PlacesRead"];

export interface FinishStateWrite {
  state: "finished";
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

// The results, the play read, finishing and the places are generated (P8),
// and so are the fields (P9).

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
// Reopening the interface adds the finals routes to the provisional paths.
export interface ProvisionalPaths {
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
}
