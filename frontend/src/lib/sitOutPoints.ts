import type { components } from "@/api/schema";

type MatchFormat = components["schemas"]["MatchFormat"];

/** The points of a sit-out the organizer can pick (FR-039, BR-071). */
export const SIT_OUT_POINTS = [0, 1, 2] as const;
export type SitOutPoints = (typeof SIT_OUT_POINTS)[number];

/**
 * The default points of a sit-out (BR-071): 1, worth a draw, only where a match
 * can end level, that is when the league allows draws and the group phase plays
 * BO1 or BO2. Otherwise 2, worth a win, so a sit-out never earns a result that
 * no match can produce. The backend computes the same default; this only shows it.
 */
export function defaultSitOutPoints(
  format: MatchFormat,
  drawsAllowed: boolean,
): 1 | 2 {
  return drawsAllowed && (format === "bo1" || format === "bo2") ? 1 : 2;
}
