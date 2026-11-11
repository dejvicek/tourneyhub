import { describe, expect, it } from "vitest";

import { defaultSitOutPoints } from "./sitOutPoints";

describe("defaultSitOutPoints (BR-071)", () => {
  it.each([
    ["bo1", true, 1],
    ["bo2", true, 1],
    ["bo3", true, 2],
    ["bo5", true, 2],
    ["bo1", false, 2],
    ["bo2", false, 2],
    ["bo3", false, 2],
    ["bo5", false, 2],
  ] as const)("is %s with draws %s -> %i", (format, draws, points) => {
    expect(defaultSitOutPoints(format, draws)).toBe(points);
  });
});
