import type { components } from "@/api/schema";

type PhaseRead = components["schemas"]["PhaseRead"];
type RoundName = components["schemas"]["RoundName"];

/** BR-084, BR-140: a knockout in the Lord have mercy mode is drawn round by round. */
export function isLordHaveMercy(phases: readonly PhaseRead[]): boolean {
  return phases.some(
    (phase) =>
      phase.kind === "knockout" &&
      phase.monster_knockout_mode === "lord_have_mercy",
  );
}

const NAMES: Partial<Record<number, RoundName>> = {
  1: "final",
  2: "semifinal",
  3: "quarterfinal",
  4: "round_of_16",
  5: "round_of_32",
  6: "round_of_64",
  7: "round_of_128",
  8: "round_of_256",
};

/**
 * What the next round to draw is called, by the rounds left (BR-140), or null
 * when every round is drawn.
 */
export function nextRoundName(k: {
  size: number;
  round_count: number;
  rounds: readonly unknown[];
}): RoundName | null {
  const left = k.round_count - k.rounds.length;
  return left < 1 ? null : (NAMES[left] ?? null);
}
