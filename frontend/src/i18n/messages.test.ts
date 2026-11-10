import { describe, expect, it } from "vitest";

import type { CsMessages } from "./locales/en";

// The checks are made by tsc (pnpm typecheck); the test only runs them.
interface Reference {
  players_one: string;
  players_other: string;
  title: string;
  nested: { rounds_other: string };
}

describe("CsMessages", () => {
  it("lets Czech add _few and _many to an English plural", () => {
    const cs: CsMessages<Reference> = {
      players_one: "{{count}} hráč",
      players_few: "{{count}} hráči",
      players_many: "{{count}} hráče",
      players_other: "{{count}} hráčů",
      title: "Hráči",
      nested: { rounds_other: "{{count}} kol", rounds_few: "{{count}} kola" },
    };

    expect(cs.players_few).toBe("{{count}} hráči");
  });

  it("refuses keys that English does not have", () => {
    const cs: CsMessages<Reference> = {
      players_one: "",
      players_other: "",
      // @ts-expect-error -- title is not a plural, so it has no _few form
      title_few: "",
      title: "",
      nested: { rounds_other: "" },
    };

    expect(cs.title).toBe("");
  });
});
