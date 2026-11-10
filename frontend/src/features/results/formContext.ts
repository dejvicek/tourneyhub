import type { PlayStandingRow, ResultWrite } from "@/demo/contract";
import type { MatchInfo } from "@/features/tournaments/play/model";

/** What both result forms need (screens 7 and 7b). */
export interface ResultFormContext {
  info: MatchInfo;
  /** Short names of the two sides, "Anna N. & Petr S.". */
  names: [string, string];
  /** First names for sentences, "Anna and Petr". */
  firstNames: [string, string];
  seeds: [number | null, number | null];
  goalsPerGame: number;
  /** Every game needs its score (BR-092). */
  required: boolean;
  drawAllowed: boolean;
  locked: boolean;
  pending: boolean;
  standings: readonly PlayStandingRow[] | undefined;
  onSave: (body: ResultWrite) => void;
}
