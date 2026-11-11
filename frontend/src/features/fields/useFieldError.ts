import { useTranslation } from "react-i18next";

import type { ApiError } from "@/api/client";

import { describeFieldError } from "./errors";

/** The message for a refused field write, or null without one (ADR-008). */
export function useFieldError(error: ApiError | null): string | null {
  const { t } = useTranslation();
  return error === null ? null : describeFieldError(error, t);
}
