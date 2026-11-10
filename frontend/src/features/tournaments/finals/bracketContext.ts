import type {
  BracketMatchData as BracketMatch,
  BracketRoundData as BracketRound,
  BracketSideData as BracketSide,
} from "@/features/finals/api";

const NO_SIDE: BracketSide = { entry_id: null, seed: null, is_bye: false };

/** A side of a match; the API's two-side tuple arrives typed as an array. */
export function sideAt(match: BracketMatch, index: 0 | 1): BracketSide {
  return match.sides[index] ?? NO_SIDE;
}

export interface BracketContext {
  sideName: (side: BracketSide) => string;
  /** Where "Enter result" goes for a match; null when it cannot be entered. */
  resultHref: (match: BracketMatch) => string | null;
  /** "Semifinal 1", "Final", "Third place". */
  matchTitle: (round: BracketRound, match: BracketMatch) => string;
}
