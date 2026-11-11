import { describe, expect, it } from "vitest";

import { defaultSitOutPoints } from "./sitOutPoints";

describe("defaultSitOutPoints (BR-071)", () => {
  it.each([
    ["bo1", 1],
    ["bo2", 1],
    ["bo3", 2],
    ["bo5", 2],
  ] as const)("is %s -> %i", (format, points) => {
    expect(defaultSitOutPoints(format)).toBe(points);
  });
});
