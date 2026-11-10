import { generatePath } from "react-router";

import type { MatchFormat, TournamentRead } from "@/demo/contract";
import { paths } from "@/lib/paths";

/** Result entry is G2's: BO1 has the beads (7), the other formats the games (7b). */
export function resultPath(
  leagueId: string,
  tournamentId: string,
  matchId: string,
  format: MatchFormat,
): string {
  return generatePath(
    format === "bo1" ? paths.enterResult : paths.bestOfResult,
    {
      leagueId,
      tournamentId,
      matchId,
    },
  );
}

/** The screen a tournament opens on, by its state and phases. */
export function landingPath(
  leagueId: string,
  tournament: Pick<TournamentRead, "id" | "state" | "phases">,
): string {
  const params = { leagueId, tournamentId: tournament.id };
  if (tournament.state === "finished") {
    return generatePath(paths.finished, params);
  }
  if (tournament.phases.some((phase) => phase.kind === "knockout")) {
    return generatePath(paths.knockout, params);
  }
  const rounds = tournament.phases.some(
    (phase) => phase.format === "swiss" || phase.format === "monster_dyp",
  );
  return generatePath(rounds ? paths.betweenRounds : paths.tournament, params);
}
