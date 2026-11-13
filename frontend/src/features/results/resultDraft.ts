// The result being entered, before it is saved: what it means and the
// whole result it sends (ADR-008). The server checks it again (BR-090,
// BR-092, BR-121); these checks only decide what the screen offers.
import type {
  GameWrite,
  MatchFormat,
  PhaseRead,
  ResultWrite,
  Side,
} from "@/demo/contract";
import { rules } from "@/lib/rules";

/** Whether every game needs its score (BR-092), as rules.ts says today. */
export function scoresRequired(phase: PhaseRead): boolean {
  switch (rules.gameScoresRequired) {
    case "swiss_and_monster_dyp":
      return phase.format === "swiss" || phase.format === "monster_dyp";
    case "when_score_difference_counts":
      return phase.format === "round_robin"
        ? rules.roundRobinTiebreakers.includes("score_difference")
        : (phase.tiebreakers ?? []).includes("score_difference");
  }
}

/** Draws only in group phases of leagues that allow them (BR-090). */
export function drawsAllowed(phase: PhaseRead, leagueAllows: boolean): boolean {
  return phase.kind === "group" && leagueAllows;
}

export type SimpleOutcome =
  | { kind: "empty" }
  | { kind: "incomplete" }
  | { kind: "needsScores" }
  | { kind: "winnerOnly"; winner: Side }
  | { kind: "win"; winner: Side; a: number; b: number }
  | { kind: "draw"; a: number }
  | { kind: "drawNotAllowed" };

/**
 * A BO1 score (screen 7). One side at the goals per game and the other
 * empty is a win without a score, when scores are optional (FR-051): the
 * three-tap result of FR-082.
 */
export function simpleOutcome(
  a: number | null,
  b: number | null,
  goalsPerGame: number,
  required: boolean,
  drawAllowed: boolean,
): SimpleOutcome {
  if (a === null && b === null) {
    return { kind: "empty" };
  }
  if (a === null || b === null) {
    const set = a ?? b ?? 0;
    if (set < goalsPerGame) {
      return { kind: "incomplete" };
    }
    return required
      ? { kind: "needsScores" }
      : { kind: "winnerOnly", winner: a === null ? "side_2" : "side_1" };
  }
  if (a === b) {
    return drawAllowed ? { kind: "draw", a } : { kind: "drawNotAllowed" };
  }
  return { kind: "win", winner: a > b ? "side_1" : "side_2", a, b };
}

export function simpleWrite(outcome: SimpleOutcome): ResultWrite | null {
  switch (outcome.kind) {
    case "winnerOnly":
      return {
        walkover_winner: null,
        games: [{ winner: outcome.winner, score_1: null, score_2: null }],
      };
    case "win":
      return {
        walkover_winner: null,
        games: [
          { winner: outcome.winner, score_1: outcome.a, score_2: outcome.b },
        ],
      };
    case "draw":
      return {
        walkover_winner: null,
        games: [{ winner: "draw", score_1: outcome.a, score_2: outcome.a }],
      };
    case "empty":
    case "incomplete":
    case "needsScores":
    case "drawNotAllowed":
      return null;
  }
}

export interface GameDraft {
  a: number | null;
  b: number | null;
  /** Picked in "Winners only" mode. */
  winner: Side | null;
}

export type EntryMode = "goals" | "winners";

export const MAX_GAMES = { bo1: 1, bo2: 2, bo3: 3, bo5: 5 } as const;
export const GAMES_TO_WIN = { bo1: 1, bo2: 2, bo3: 2, bo5: 3 } as const;

/** The winner of one game in the chosen mode; null while it is open. */
export function gameWinner(game: GameDraft, mode: EntryMode): Side | null {
  if (mode === "winners") {
    return game.winner;
  }
  if (game.a === null || game.b === null || game.a === game.b) {
    return null;
  }
  return game.a > game.b ? "side_1" : "side_2";
}

export interface Series {
  /** Games won by each side, counting only the games that are needed. */
  wins: [number, number];
  /** How many games the series has played or needs before it is decided. */
  needed: number;
  /** The side that won the match, "draw" for a BO2 1:1, null while open. */
  outcome: Side | "draw" | null;
}

/** A BO2, BO3 or BO5 series from its games (BR-121). */
export function series(
  games: readonly GameDraft[],
  format: MatchFormat,
  mode: EntryMode,
): Series {
  const need = GAMES_TO_WIN[format];
  const wins: [number, number] = [0, 0];
  let needed = 0;
  for (const game of games.slice(0, MAX_GAMES[format])) {
    if (format !== "bo2" && Math.max(...wins) >= need) {
      break;
    }
    needed += 1;
    const winner = gameWinner(game, mode);
    if (winner === null) {
      return { wins, needed, outcome: null };
    }
    wins[winner === "side_1" ? 0 : 1] += 1;
  }
  if (format === "bo2") {
    return {
      wins,
      needed: 2,
      outcome:
        wins[0] + wins[1] < 2
          ? null
          : wins[0] === wins[1]
            ? "draw"
            : wins[0] > wins[1]
              ? "side_1"
              : "side_2",
    };
  }
  const outcome =
    wins[0] >= need ? "side_1" : wins[1] >= need ? "side_2" : null;
  return { wins, needed: outcome === null ? needed + 1 : needed, outcome };
}

/** The whole best-of result, or null while it is not complete. */
export function seriesWrite(
  games: readonly GameDraft[],
  format: MatchFormat,
  mode: EntryMode,
  drawAllowed: boolean,
): ResultWrite | null {
  const result = series(games, format, mode);
  if (result.outcome === null || (result.outcome === "draw" && !drawAllowed)) {
    return null;
  }
  const written: GameWrite[] = games.slice(0, result.needed).map((game) => ({
    winner: gameWinner(game, mode) ?? "draw",
    score_1: mode === "goals" ? game.a : null,
    score_2: mode === "goals" ? game.b : null,
  }));
  return { walkover_winner: null, games: written };
}
