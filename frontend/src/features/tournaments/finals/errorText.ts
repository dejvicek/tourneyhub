import type { TFunction } from "i18next";

import { ApiError, type ErrorCode } from "@/api/client";

/** The refusals of the knockout's writes with a text of their own (ADR-008). */
const CODE_TEXTS = {
  group_phase_not_done: "finals.errors.groupNotDone",
  qualifiers_out_of_range: "finals.errors.qualifiers",
  format_not_supported: "finals.errors.formatNotSupported",
  knockout_mode_not_applicable: "finals.errors.modeNotApplicable",
  phase_not_deletable: "finals.errors.phaseNotDeletable",
  season_closed: "finals.errors.seasonClosed",
  qualifiers_changed: "finals.errors.qualifiersChanged",
  match_has_result: "finals.errors.finalHasResult",
} as const satisfies Partial<Record<ErrorCode, string>>;

function hasText(code: ErrorCode | undefined): code is keyof typeof CODE_TEXTS {
  return code !== undefined && code in CODE_TEXTS;
}

/** What a failed write says: 409 and 404 mean the data changed and was reloaded (ADR-008). */
export function errorText(t: TFunction, error: unknown): string {
  if (error instanceof ApiError) {
    if (hasText(error.code)) {
      return t(CODE_TEXTS[error.code], {
        minimum: Number(error.detail.minimum),
        maximum: Number(error.detail.maximum),
      });
    }
    if (error.status === 409 || error.status === 404) {
      return t("finals.common.stale");
    }
    if (error.status === 422) {
      return t("finals.common.refused");
    }
  }
  return t("finals.common.failed");
}
