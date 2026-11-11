import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";
import { i18n } from "@/i18n";

import { describeError } from "./errors";

const refused = (status: number, code: string, detail: object = {}) =>
  new ApiError(status, { code, detail });

describe("the texts for a refused start or back to setup", () => {
  it.each([
    [
      "en",
      refused(422, "not_enough_entries", { minimum: 2, given: 1 }),
      "Not enough entries: at least 2 are needed.",
    ],
    [
      "en",
      refused(422, "players_without_partner", { unpaired: 1 }),
      "1 player has no partner yet.",
    ],
    [
      "cs",
      refused(422, "players_without_partner", { unpaired: 3 }),
      "3 hráči ještě nemají spoluhráče.",
    ],
    [
      "en",
      refused(422, "tournament_has_results", { results: 1 }),
      "Going back to setup is possible only until the first result.",
    ],
    [
      "en",
      refused(409, "tournament_not_in_progress", { state: "setup" }),
      "This changed on another device. The screen shows the current state.",
    ],
  ])("%s: %o", async (language, error, text) => {
    await i18n.changeLanguage(language);

    expect(describeError(error, i18n.t)).toBe(text);
  });
});
