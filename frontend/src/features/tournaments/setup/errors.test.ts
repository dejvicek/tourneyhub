import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";
import { i18n } from "@/i18n";

import { describeError, describeRefusal } from "./errors";

const refused = (status: number, code: string, detail: object = {}) =>
  new ApiError(status, { code, detail });

describe("the texts for a refused start or back to setup", () => {
  it.each([
    [
      "en",
      refused(422, "sit_out_points_not_applicable"),
      "A round robin has no points for sitting out.",
    ],
    [
      "cs",
      refused(422, "sit_out_points_not_applicable"),
      "Každý s každým nemá body za volno.",
    ],
    [
      "en",
      refused(422, "not_enough_entries", { minimum: 2, given: 1 }),
      "Not enough entries: at least 2 are needed.",
    ],
    [
      "en",
      refused(422, "too_many_entries_for_round_robin", { limit: 64 }),
      "A round robin takes at most 64 entries. Remove some, or pick another format.",
    ],
    [
      "cs",
      refused(422, "too_many_entries_for_round_robin", { limit: 64 }),
      "Každý s každým má nejvýše 64 účastníků. Odeberte některé, nebo zvolte jiný formát.",
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
      refused(409, "seed_order_changed"),
      "The seeds changed on another device. Check the first round and start again.",
    ],
    [
      "cs",
      refused(409, "seed_order_changed"),
      "Nasazení se změnilo na jiném zařízení. Zkontrolujte první kolo a spusťte turnaj znovu.",
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

describe("the texts for a refusal that the preview names", () => {
  it("uses the same text as the refused start", async () => {
    await i18n.changeLanguage("en");

    expect(describeRefusal("not_enough_entries", { minimum: 4 }, i18n.t)).toBe(
      describeError(refused(422, "not_enough_entries", { minimum: 4 }), i18n.t),
    );
  });

  it("falls back to the generic text for a code it has no text for", async () => {
    await i18n.changeLanguage("en");

    expect(describeRefusal("tournament_not_in_setup", {}, i18n.t)).toBe(
      i18n.t("tournaments.errors.generic"),
    );
  });
});
