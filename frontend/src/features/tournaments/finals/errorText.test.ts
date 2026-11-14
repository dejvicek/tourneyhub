import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";
import { i18n } from "@/i18n";

import { errorText } from "./errorText";

const refused = (code: string) => new ApiError(422, { code, detail: {} });

describe("errorText", () => {
  it.each([
    ["en", "late_entry_not_allowed", "This tournament takes no late players."],
    [
      "en",
      "player_already_in_tournament",
      "This player is already in the tournament.",
    ],
    [
      "cs",
      "late_entry_not_allowed",
      "Do tohoto turnaje se hráči přihlásit později nemohou.",
    ],
    ["cs", "player_already_in_tournament", "Tento hráč už v turnaji je."],
  ])("shows its own text in %s for %s (FR-047)", (language, code, text) => {
    expect(errorText(i18n.getFixedT(language), refused(code))).toBe(text);
  });
});
