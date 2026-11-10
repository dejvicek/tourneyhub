import type { TournamentType } from "./format";

/** How many entries (players or pairs) a number of picked players makes. */
export function entryCount(type: TournamentType, players: number): number {
  switch (type) {
    case "singles":
    case "monster_dyp":
      return players;
    case "doubles":
    case "dyp":
      return Math.floor(players / 2);
  }
}

/** Round robin sizes (BR-050): every entry meets every other once or twice. */
export function roundRobinSize(
  entries: number,
  legs: 1 | 2,
): { matches: number; rounds: number } {
  const roundsOnce = entries % 2 === 0 ? entries - 1 : entries;
  return {
    matches: ((entries * (entries - 1)) / 2) * legs,
    rounds: Math.max(roundsOnce, 0) * legs,
  };
}

/** The fewest players a type needs (FR-032, BR-031), for the picked list. */
export function minimumPlayers(
  type: TournamentType,
  thirdPlaceMatch: boolean,
  noGroupPhase: boolean,
): number {
  switch (type) {
    case "singles":
      return noGroupPhase && thirdPlaceMatch ? 4 : 2;
    case "doubles":
    case "dyp":
    case "monster_dyp":
      return 4;
  }
}
