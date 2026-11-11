import type { components } from "@/api/schema";

type MatchFormat = components["schemas"]["MatchFormat"];

/** The points of a sit-out the organizer can pick (FR-039, BR-071). */
export const SIT_OUT_POINTS = [0, 1, 2] as const;
export type SitOutPoints = (typeof SIT_OUT_POINTS)[number];

/**
 * The default points of a sit-out for a group phase's match format (BR-071):
 * a BO1 or BO2 match can end level, so a sit-out is worth a draw (1); a BO3 or
 * BO5 match cannot, so it is worth a win (2). The league's draw setting plays
 * no part. The backend computes the same default; this only shows it.
 */
export function defaultSitOutPoints(format: MatchFormat): 1 | 2 {
  return format === "bo1" || format === "bo2" ? 1 : 2;
}
