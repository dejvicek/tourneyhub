// The demo's fixed ids. Each area of the seed has its own range of numbers,
// so seed files written in parallel never give two rows the same id.

/** The areas of the seed and their id ranges (src/demo/README.md). */
export const SEED_AREAS = {
  foundation: [1, 999],
  setup: [1000, 1999],
  play: [2000, 2999],
  finals: [3000, 3999],
  outside: [4000, 4999],
} as const satisfies Record<string, readonly [number, number]>;

export type SeedArea = keyof typeof SEED_AREAS;

/**
 * An id in UUIDv7 form; fixed, so links into the demo stay valid. Given an
 * area, `n` must lie in its range. Rows the demo creates at run time pass no
 * area.
 */
export function testId(n: number, area?: SeedArea): string {
  if (area !== undefined) {
    const [first, last] = SEED_AREAS[area];
    if (!Number.isInteger(n) || n < first || n > last) {
      throw new RangeError(
        `Test id ${String(n)} is outside the ${area} range ${String(first)}–${String(last)}`,
      );
    }
  }
  return `019a0000-0000-7000-8000-${n.toString(16).padStart(12, "0")}`;
}

export const TEST_USER_ID = testId(1, "foundation");
export const TEST_LEAGUE_ID = testId(2, "foundation");
export const TEST_SEASON_ID = testId(3, "foundation");
export const TEST_SHARE_TOKEN = "demo-share-token-k3vQ9xLr2TbW8sNe";
export const TEST_EMAIL = "organizer@demo.tourneyhub.test";
