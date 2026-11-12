/** The points for sitting out the organizer can pick (FR-039, BR-071, BR-075). */
export const SIT_OUT_POINTS = [0, 1, 2] as const;
export type SitOutPoints = (typeof SIT_OUT_POINTS)[number];

/**
 * The default points for sitting out in Swiss and Monster DYP (FR-039). It does
 * not depend on the match format or the league's draw setting. A round robin
 * has none (BR-071).
 */
export const DEFAULT_SIT_OUT_POINTS: SitOutPoints = 0;
