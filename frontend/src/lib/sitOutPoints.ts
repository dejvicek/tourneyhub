import type { components } from "@/api/schema";

type MatchFormat = components["schemas"]["MatchFormat"];

/**
 * The points of a sit-out the organizer can pick (FR-039, BR-071, BR-075).
 * Only a Swiss or Monster DYP phase has them; a round robin has none, not even
 * 0 (BR-071). The code still offers them for a round robin; PR #65 (closes #59)
 * changes that.
 */
export const SIT_OUT_POINTS = [0, 1, 2] as const;
export type SitOutPoints = (typeof SIT_OUT_POINTS)[number];

/**
 * The default points of a sit-out for a group phase's match format: a BO1 or
 * BO2 match can end level, so a sit-out is worth a draw (1); a BO3 or BO5
 * match cannot, so it is worth a win (2). The backend computes the same
 * default; this only shows it.
 *
 * This does NOT yet follow the PRD. FR-039 makes the default 0, with nothing
 * following the match format or the league's draw setting; the organizer picks
 * 0, 1 or 2 (BR-075). PR #65 changes the behaviour (and a round robin without
 * any value).
 */
export function defaultSitOutPoints(format: MatchFormat): 1 | 2 {
  return format === "bo1" || format === "bo2" ? 1 : 2;
}
