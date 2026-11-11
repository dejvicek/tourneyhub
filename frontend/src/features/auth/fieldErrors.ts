import type { TFunction } from "i18next";

import { type ValidationProblem, validationProblems } from "./apiErrors";

/** A 422 validation problem as a sentence (P2b, P5a share the types). */
export function problemMessage(t: TFunction, problem: ValidationProblem) {
  const { min_length: min, max_length: max } = problem.context;
  switch (problem.type) {
    case "string_too_short":
    case "too_short":
      return min === undefined || min <= 1
        ? t("auth.errors.nameRequired")
        : t("auth.errors.tooShort", { count: min });
    case "string_too_long":
      return t("auth.errors.nameTooLong", { count: max ?? 100 });
    case "less_than_equal":
      return t("auth.errors.tooLarge", { count: problem.context.le ?? 0 });
    case "string_pattern_mismatch":
      return t("auth.errors.emailInvalid");
    case "invisible_characters":
      return t("auth.errors.invisible");
    default:
      return t("auth.errors.generic");
  }
}

/** The messages of a 422 per field of the request body. */
export function fieldErrors(
  t: TFunction,
  error: unknown,
): Partial<Record<string, string>> {
  const messages: Partial<Record<string, string>> = {};
  for (const problem of validationProblems(error)) {
    if (problem.field !== undefined) {
      messages[problem.field] ??= problemMessage(t, problem);
    }
  }
  return messages;
}
