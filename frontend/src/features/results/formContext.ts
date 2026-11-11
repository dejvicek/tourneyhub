import type { ReactNode } from "react";

import type { components } from "@/api/schema";
import type { MatchInfo } from "@/features/tournaments/play/model";

type PlayStandingRow = components["schemas"]["PlayStandingRow"];
type ResultWrite = components["schemas"]["ResultWrite"];

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
  /** What goes under "Save result", in the sheet's sticky footer: errors, the walkover and clearing. */
  actions: ReactNode;
}
