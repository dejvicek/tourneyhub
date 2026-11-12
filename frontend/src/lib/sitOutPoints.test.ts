import { describe, expect, it } from "vitest";

import { DEFAULT_SIT_OUT_POINTS, SIT_OUT_POINTS } from "./sitOutPoints";

describe("sit-out points", () => {
  it("default to 0 (FR-039)", () => {
    expect(DEFAULT_SIT_OUT_POINTS).toBe(0);
  });

  it("are 0, 1 or 2 (BR-071)", () => {
    expect(SIT_OUT_POINTS).toEqual([0, 1, 2]);
  });
});
