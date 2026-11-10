import { generatePath } from "react-router";

import { paths } from "@/lib/paths";

/**
 * Result entry is an overlay of the knockout or the rounds screen (7 or 7b,
 * chosen by the overlay from the match's format), not a screen of ours.
 */
export function resultPath(
  area: "knockout" | "rounds",
  leagueId: string,
  tournamentId: string,
  matchId: string,
): string {
  return generatePath(
    area === "knockout" ? paths.knockoutResult : paths.roundsResult,
    { leagueId, tournamentId, matchId },
  );
}
