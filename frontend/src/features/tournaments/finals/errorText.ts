import type { TFunction } from "i18next";

import { ApiError } from "@/api/client";

/** What a failed write says: 409 and 404 mean the data changed and was reloaded (ADR-008). */
export function errorText(t: TFunction, error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409 || error.status === 404) {
      return t("finals.common.stale");
    }
    if (error.status === 422) {
      return t("finals.common.refused");
    }
  }
  return t("finals.common.failed");
}
