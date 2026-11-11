import type { components } from "@/api/schema";

type MatchFormat = components["schemas"]["MatchFormat"];

/**
 * The points of a sit-out the organizer can pick (FR-039, BR-071, BR-076).
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
 * This does NOT yet follow the PRD. BR-075 and FR-039 make the default 1 when
 * a group-phase match can be drawn (BR-090, so the league must allow draws),
 * otherwise 2, so the league's draw setting does play a part, and the default
 * moves with the match format (FR-054) and the draw setting (BR-013) for as
 * long as the phase has no result (BR-077), unless the organizer picked a value
 * (BR-076). PR #65 (closes #59) changes the behaviour (a round robin without
 * any value).
 */
export function defaultSitOutPoints(format: MatchFormat): 1 | 2 {
  return format === "bo1" || format === "bo2" ? 1 : 2;
}
