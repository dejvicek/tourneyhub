import { describe, expect, it } from "vitest";

// frontend-style §2 and §4: an eslint-disable names its rules and gives a
// reason after " -- ", and an effect's dependencies are never suppressed.
const sources = import.meta.glob<string>(
  ["/src/**/*.{ts,tsx}", "/e2e/**/*.ts", "!/src/api/schema.d.ts"],
  { query: "?raw", import: "default", eager: true },
);

// Built from pieces, so this file does not match itself.
const directive = new RegExp(
  String.raw`\/[/*]\s*eslint-${"disable"}(?:-next-line|-line)?(?=\s|\*\/|$)(.*)`,
  "g",
);

function disables(): { where: string; rest: string }[] {
  return Object.entries(sources).flatMap(([file, text]) =>
    text.split("\n").flatMap((line, index) =>
      [...line.matchAll(directive)].map((match) => ({
        where: `${file}:${String(index + 1)}`,
        rest: (match[1] ?? "").replace(/\*\/.*$/, ""),
      })),
    ),
  );
}

describe("eslint-disable comments", () => {
  it("finds the source files", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(50);
  });

  it("name their rules and give a reason after ' -- '", () => {
    const bare = disables()
      .filter(({ rest }) => !/^\s+\S+.*\s--\s+\S/.test(rest))
      .map(({ where }) => where);

    expect(bare).toEqual([]);
  });

  it("never switch off react-hooks/exhaustive-deps", () => {
    const suppressed = disables()
      .filter(({ rest }) => rest.split(" -- ")[0]?.includes("exhaustive-deps"))
      .map(({ where }) => where);

    expect(suppressed).toEqual([]);
  });
});
