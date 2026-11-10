import type { TFunction } from "i18next";

import { ApiError } from "@/api/client";

/** The rules a 422 from setup names in `detail.rule`, and their texts. */
const RULE_TEXTS = {
  name_required: "tournaments.errors.rules.name_required",
  positive_numbers: "tournaments.errors.rules.positive_numbers",
  "FR-031": "tournaments.errors.rules.fr031",
  "BR-121": "tournaments.errors.rules.br121",
  "BR-002": "tournaments.errors.rules.br002",
  "BR-003": "tournaments.errors.rules.br003",
  "FR-036": "tournaments.errors.rules.fr036",
  "FR-038": "tournaments.errors.rules.fr038",
} as const satisfies Record<string, string>;

function isRule(rule: unknown): rule is keyof typeof RULE_TEXTS {
  return typeof rule === "string" && rule in RULE_TEXTS;
}

/**
 * The text for a failed setup call. A 409 is not an error to the organizer:
 * the screen reloaded and shows what changed (ADR-008), so it has its own
 * message; a 422 names the rule that refused the request.
 */
export function describeError(error: unknown, t: TFunction): string {
  if (error instanceof ApiError) {
    if (error.status === 409 || error.status === 404) {
      return t("tournaments.errors.changed");
    }
    if (error.status === 422) {
      const rule = error.detail.rule;
      if (rule === "FR-032") {
        return t("tournaments.errors.rules.fr032", {
          min: Number(error.detail.min),
          given: Number(error.detail.given),
        });
      }
      if (isRule(rule)) {
        return t(RULE_TEXTS[rule]);
      }
    }
  }
  return t("tournaments.errors.generic");
}

/** True for the 409 and 404 that mean "this changed elsewhere; reloaded". */
export function isChanged(error: unknown): boolean {
  return (
    error instanceof ApiError && (error.status === 409 || error.status === 404)
  );
}
