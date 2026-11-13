// Short names for the API types the fake API and its tests use. Most are
// aliases of generated types (src/api/schema.d.ts); the provisional paths
// themselves are in src/api/provisionalPaths.ts. Grouped by area, like the
// handlers in src/demo/handlers/.
import type { components } from "@/api/schema";

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

// The Swiss rounds and tie-breakers (P12): generated. Adding a round carries
// the number the organizer expects (ADR-008); the standings come from the
// play read and the share link's standings.
export type SwissRoundRead = components["schemas"]["SwissRoundRead"];

// The places (P8 for a round robin without a knockout): generated.
export type PlaceReason = components["schemas"]["PlaceReasonRead"];
export type PlaceDetail = components["schemas"]["PlaceRead"];
export type PlacesRead = components["schemas"]["PlacesRead"];

// The results, the play read, finishing and the places are generated (P8),
// and so are the fields (P9).
