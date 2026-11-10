import { useTranslation } from "react-i18next";

import type { ApiError } from "@/api/client";

/** The message for a refused field write (ADR-008: 409 reloads, 422 explains). */
export function useFieldError(error: ApiError | null): string | null {
  const { t } = useTranslation();
  if (error === null) {
    return null;
  }
  if (error.status === 409 || error.status === 404) {
    return t("fields.errors.changed");
  }
  switch (error.detail.rule) {
    case "BR-131":
      return t("fields.errors.twoFields");
    case "BR-132":
      return t("fields.errors.lastField");
    default:
      return t("fields.errors.generic");
  }
}
