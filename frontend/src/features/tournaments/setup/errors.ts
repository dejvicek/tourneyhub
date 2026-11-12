import type { TFunction } from "i18next";

import { ApiError, type ErrorCode } from "@/api/client";

/** The 422 codes of setup and their texts (ADR-008). */
const CODE_TEXTS = {
  draws_not_allowed: "tournaments.errors.rules.br121",
  sit_out_points_not_applicable: "tournaments.errors.rules.br071",
  nothing_to_pair: "tournaments.errors.rules.fr033",
  not_enough_players: "tournaments.errors.rules.fr032",
  dyp_halves_unequal: "tournaments.errors.rules.br032Unequal",
  too_many_left_out: "tournaments.errors.rules.br032LeftOut",
  dyp_halves_incomplete: "tournaments.errors.rules.br032Incomplete",
  not_enough_entries: "tournaments.errors.rules.fr032Entries",
  players_without_partner: "tournaments.errors.rules.br030",
  too_many_entries_for_round_robin: "tournaments.errors.rules.fr032Max",
  format_not_supported: "tournaments.errors.rules.fr035",
  tournament_has_results: "tournaments.errors.rules.fr036",
} as const satisfies Partial<Record<ErrorCode, string>>;

function hasText<T extends object>(texts: T, key: unknown): key is keyof T {
  return typeof key === "string" && key in texts;
}

/**
 * The text for a refusal of the API: the 422 that names the rule, as an error
 * or as the preview's `problem` (ADR-008). Any other code has the generic text.
 */
export function describeRefusal(
  code: ErrorCode | undefined,
  detail: Record<string, unknown>,
  t: TFunction,
): string {
  const values = {
    min: Number(detail.minimum),
    limit: Number(detail.limit),
    count: Number(detail.unpaired),
    top: Number(detail.top),
    bottom: Number(detail.bottom),
  };
  if (hasText(CODE_TEXTS, code)) {
    return t(CODE_TEXTS[code], values);
  }
  return t("tournaments.errors.generic");
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
  return describeRefusal(error.code, error.detail, t);
}

/** True for the 409 and 404 that mean "this changed elsewhere; reloaded". */
export function isChanged(error: unknown): boolean {
  return (
    error instanceof ApiError && (error.status === 409 || error.status === 404)
  );
}
