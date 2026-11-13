// Stand-ins for the request and response types of routes the backend does
// not have yet: the Swiss and Monster DYP ranking, the participants, adding
// and deleting a round, late players and disabling, and the tie-breakers
// (FR-043, P12). The demo's contract (src/demo/contract.ts) builds its
// provisional paths on them, and the screens read them from here. Each type
// goes away once its route is generated into schema.d.ts (D3, D4).
import type { components } from "./schema";

type Uuid = string;
type Tiebreaker = components["schemas"]["Tiebreaker"];

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
  tiebreakers: Tiebreaker[];
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
  tiebreakers: Tiebreaker[];
}
