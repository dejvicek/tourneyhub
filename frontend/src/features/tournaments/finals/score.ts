import type { MatchFormat, MatchRead } from "@/demo/contract";

/** The score a result list shows: a BO1 game's goals, otherwise the games won. */
export function scoreOf(
  match: Pick<MatchRead, "outcome" | "games">,
  format: MatchFormat,
): [number, number] | null {
  if (match.outcome === null || match.games.length === 0) {
    return null;
  }
  const first = match.games[0];
  if (
    format === "bo1" &&
    first?.score_1 !== null &&
    first?.score_1 !== undefined &&
    first.score_2 !== null
  ) {
    return [first.score_1, first.score_2];
  }
  const tally: [number, number] = [0, 0];
  for (const game of match.games) {
    if (game.winner === "side_1") {
      tally[0] += 1;
    } else if (game.winner === "side_2") {
      tally[1] += 1;
    }
  }
  return tally;
}
