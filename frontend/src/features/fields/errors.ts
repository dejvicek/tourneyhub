import type { TFunction } from "i18next";

import type { ApiError, ErrorCode } from "@/api/client";

/** The 422 codes of the field writes and their texts (ADR-008). */
const CODE_TEXTS = {
  player_on_another_field: "fields.errors.twoFields",
  last_field: "fields.errors.lastField",
  match_sides_unknown: "fields.errors.sidesUnknown",
  placement_changed: "fields.errors.placementChanged",
  tournament_not_in_progress: "fields.errors.notInProgress",
  field_not_found: "fields.errors.fieldRemoved",
} as const satisfies Partial<Record<ErrorCode, string>>;

function hasText(code: ErrorCode | undefined): code is keyof typeof CODE_TEXTS {
  return code !== undefined && code in CODE_TEXTS;
}

/**
 * The text for a refused field write (ADR-008). A 409 or a 404 comes from a
 * stale screen, which the write's reload repairs: some codes have a text of
 * their own, such as a field already removed (the 404 of a repeated delete,
 * which means the delete happened), the rest "changed elsewhere". A 422
 * names the rule the organizer ran into. Any other refusal has the generic
 * text.
 */
export function describeFieldError(error: ApiError, t: TFunction): string {
  if (hasText(error.code)) {
    return t(CODE_TEXTS[error.code]);
  }
  if (error.status === 409 || error.status === 404) {
    return t("fields.errors.changed");
  }
  return t("fields.errors.generic");
}
