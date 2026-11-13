import { describe, expect, it } from "vitest";

import { pairPlaces } from "./placePairs";

const row = (entry: string, place: number, partner: string | null = null) => ({
  entry_id: entry,
  place,
  reason: { partner_entry_id: partner },
});

describe("pairPlaces", () => {
  it("joins partners into one line (BR-145)", () => {
    const groups = pairPlaces([row("a", 1, "b"), row("b", 1, "a")]);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.entryIds).toEqual(["a", "b"]);
    expect(groups[0]?.place).toBe(1);
    expect(groups[0]?.first.entry_id).toBe("a");
  });

  it("keeps 4 semifinal losers as two pairs sharing 3rd (BR-145)", () => {
    const groups = pairPlaces([
      row("a", 3, "c"),
      row("b", 3, "d"),
      row("c", 3, "a"),
      row("d", 3, "b"),
    ]);
    expect(groups.map((g) => g.entryIds)).toEqual([
      ["a", "c"],
      ["b", "d"],
    ]);
  });

  it("passes a row without a partner through", () => {
    const groups = pairPlaces([row("a", 1), row("b", 2, "x")]);
    expect(groups.map((g) => g.entryIds)).toEqual([["a"], ["b"]]);
  });
});
