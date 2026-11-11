import type { TFunction } from "i18next";

import type { ApiError, ErrorCode } from "@/api/client";

/** The 422 codes of the field writes and their texts (ADR-008). */
const CODE_TEXTS = {
  player_on_another_field: "fields.errors.twoFields",
  last_field: "fields.errors.lastField",
  match_sides_unknown: "fields.errors.sidesUnknown",
} as const satisfies Partial<Record<ErrorCode, string>>;

function hasText(code: ErrorCode | undefined): code is keyof typeof CODE_TEXTS {
  return code !== undefined && code in CODE_TEXTS;
}

/**
 * The text for a refused field write (ADR-008). A 409 or a 404 comes from a
 * stale screen, which the write's reload repairs; a 422 names the rule the
 * organizer ran into. Any other refusal has the generic text.
 */
export function describeFieldError(error: ApiError, t: TFunction): string {
  if (error.status === 409 || error.status === 404) {
    return t("fields.errors.changed");
  }
  return hasText(error.code)
    ? t(CODE_TEXTS[error.code])
    : t("fields.errors.generic");
}
