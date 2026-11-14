import { describe, expect, it } from "vitest";

import { nextRoundName } from "./remix";

describe("nextRoundName", () => {
  it("names the next round from the rounds left (BR-140)", () => {
    const rounds = [{}];
    expect(nextRoundName({ size: 16, round_count: 4, rounds })).toBe(
      "quarterfinal",
    );
    expect(nextRoundName({ size: 16, round_count: 4, rounds: [] })).toBe(
      "round_of_16",
    );
    expect(
      nextRoundName({ size: 16, round_count: 4, rounds: [{}, {}, {}] }),
    ).toBe("final");
    expect(
      nextRoundName({ size: 16, round_count: 4, rounds: [{}, {}, {}, {}] }),
    ).toBeNull();
  });
});
