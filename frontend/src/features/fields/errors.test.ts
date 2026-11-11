import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";
import { i18n } from "@/i18n";

import { describeFieldError } from "./errors";

const refused = (status: number, code: string, detail: object = {}) =>
  new ApiError(status, { code, detail });

describe("the texts for a refused field write (ADR-008)", () => {
  it.each([
    [
      "en",
      refused(422, "player_on_another_field", {
        player_ids: [],
        field_ids: [],
      }),
      "That would put a player on two fields at once.",
    ],
    [
      "cs",
      refused(422, "player_on_another_field", {
        player_ids: [],
        field_ids: [],
      }),
      "Tím by hráč hrál na dvou hřištích najednou.",
    ],
    ["en", refused(422, "last_field"), "The last field can't be removed."],
    ["cs", refused(422, "last_field"), "Poslední hřiště nejde odebrat."],
    [
      "en",
      refused(422, "match_sides_unknown"),
      "This match can't be played yet: a side isn't known.",
    ],
    [
      "en",
      refused(409, "field_not_free", { field_id: "f", match_id: "m" }),
      "The fields changed elsewhere. They were reloaded.",
    ],
    [
      "cs",
      refused(409, "field_number_changed", { number: 4 }),
      "Hřiště se mezitím změnila. Byla znovu načtena.",
    ],
    [
      "en",
      refused(404, "field_not_found"),
      "The fields changed elsewhere. They were reloaded.",
    ],
    [
      "en",
      refused(422, "validation_failed"),
      "The fields could not be changed. Try again.",
    ],
  ])("%s: %o", async (language, error, text) => {
    await i18n.changeLanguage(language);

    expect(describeFieldError(error, i18n.t)).toBe(text);
  });
});
