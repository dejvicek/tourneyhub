import { describe, expect, it } from "vitest";

import { type CsMessages, en } from "./locales/en";

// The type checks are made by tsc (pnpm typecheck); the tests only run them.
interface Reference {
  players_one: string;
  players_other: string;
  title: string;
  nested: { rounds_other: string };
}

function isTree(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** The paths of all keys in a message tree, such as "finals.summary_one". */
function keyPaths(tree: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    isTree(value) ? keyPaths(value, `${prefix}${key}.`) : [`${prefix}${key}`],
  );
}

describe("English messages", () => {
  it("use only the plural forms _one and _other (frontend-style §7)", () => {
    const paths = keyPaths(en);
    const otherForms = paths.filter((path) =>
      /_(zero|two|few|many)$/.test(path),
    );

    expect(paths.length).toBeGreaterThan(100);
    expect(otherForms).toEqual([]);
  });
});

describe("CsMessages", () => {
  it("needs _few and _many beside an English plural", () => {
    const cs: CsMessages<Reference> = {
      players_one: "{{count}} hráč",
      players_few: "{{count}} hráči",
      players_many: "{{count}} hráče",
      players_other: "{{count}} hráčů",
      title: "Hráči",
      nested: {
        rounds_other: "{{count}} kol",
        rounds_few: "{{count}} kola",
        rounds_many: "{{count}} kola",
      },
    };

    expect(cs.players_few).toBe("{{count}} hráči");
  });

  it("refuses a Czech plural without _many", () => {
    // @ts-expect-error -- players_many is missing
    const cs: CsMessages<Reference> = {
      players_one: "",
      players_few: "",
      players_other: "",
      title: "",
      nested: { rounds_other: "", rounds_few: "", rounds_many: "" },
    };

    expect(cs.title).toBe("");
  });

  it("refuses keys that English does not have", () => {
    const cs: CsMessages<Reference> = {
      players_one: "",
      players_few: "",
      players_many: "",
      players_other: "",
      // @ts-expect-error -- title is not a plural, so it has no _few form
      title_few: "",
      title: "",
      nested: { rounds_other: "", rounds_few: "", rounds_many: "" },
    };

    expect(cs.title).toBe("");
  });
});
