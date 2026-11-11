import type { TFunction } from "i18next";

import type {
  BracketData,
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
  /** Whether the viewer may change results (the organizer, not the share link). */
  canChange: boolean;
  resultHref: (match: BracketMatch) => string | null;
  /** "Semifinal 1", "Final", "Third place". */
  /** The title of the match with this number in the tournament ("Semifinal 1"). */
  titleOfNumber: (number: number) => string;
  matchTitle: (round: BracketRound, match: BracketMatch) => string;
}

/** The one name of each match, "Quarterfinal 1", on every screen and size. */
export function bracketTitles(
  t: TFunction,
  bracket: BracketData | undefined,
): Pick<BracketContext, "matchTitle" | "titleOfNumber"> {
  const matchTitle = (round: BracketRound, match: BracketMatch) =>
    match.kind === "third_place"
      ? t("finals.matchTitle.third_place")
      : t(`finals.matchTitle.${round.name}`, { n: match.position });
  return {
    matchTitle,
    titleOfNumber: (number) => {
      for (const round of bracket?.rounds ?? []) {
        const found = round.matches.find((m) => m.number === number);
        if (found !== undefined) {
          return matchTitle(round, found);
        }
      }
      return String(number);
    },
  };
}
