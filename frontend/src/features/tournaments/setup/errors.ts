import type { TFunction } from "i18next";

import { ApiError, type ErrorCode } from "@/api/client";

/** The 422 codes of setup and their texts (ADR-008). */
const CODE_TEXTS = {
  draws_not_allowed: "tournaments.errors.rules.br121",
  nothing_to_pair: "tournaments.errors.rules.fr033",
  not_enough_players: "tournaments.errors.rules.fr032",
  dyp_halves_unequal: "tournaments.errors.rules.br032Unequal",
  too_many_left_out: "tournaments.errors.rules.br032LeftOut",
  dyp_halves_incomplete: "tournaments.errors.rules.br032Incomplete",
} as const satisfies Partial<Record<ErrorCode, string>>;

/** The rules the demo's provisional start and "back to setup" name in `detail.rule`. */
const RULE_TEXTS = {
  "FR-032": "tournaments.errors.rules.fr032",
  "FR-036": "tournaments.errors.rules.fr036",
} as const satisfies Record<string, string>;

function hasText<T extends object>(texts: T, key: unknown): key is keyof T {
  return typeof key === "string" && key in texts;
}

/**
 * The text for a failed setup call. A 409 is not an error to the organizer:
 * the screen reloaded and shows what changed (ADR-008), so it has its own
 * message; a 422 names the rule that refused the request.
 */
export function describeError(error: unknown, t: TFunction): string {
  if (!(error instanceof ApiError)) {
    return t("tournaments.errors.generic");
  }
  if (isChanged(error)) {
    return t("tournaments.errors.changed");
  }
  const { detail } = error;
  const values = {
    min: Number(detail.minimum ?? detail.min),
    top: Number(detail.top),
    bottom: Number(detail.bottom),
  };
  if (hasText(CODE_TEXTS, error.code)) {
    return t(CODE_TEXTS[error.code], values);
  }
  if (error.code === "validation_failed" && hasText(RULE_TEXTS, detail.rule)) {
    return t(RULE_TEXTS[detail.rule], values);
  }
  return t("tournaments.errors.generic");
}

/** True for the 409 and 404 that mean "this changed elsewhere; reloaded". */
export function isChanged(error: unknown): boolean {
  return (
    error instanceof ApiError && (error.status === 409 || error.status === 404)
  );
}
