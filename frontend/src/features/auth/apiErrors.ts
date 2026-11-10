// Reading an ApiError's code and detail (ADR-008). The generated ErrorCode
// does not list P2b's, P5a's and the players proposal's codes yet; they
// arrive in the same shape, so the code is read as either.
import { ApiError, type ErrorCode } from "@/api/client";
import type { OutsideErrorCode } from "@/demo/contract";

export type KnownErrorCode = ErrorCode | OutsideErrorCode;

export function errorCodeOf(error: unknown): KnownErrorCode | undefined {
  if (!(error instanceof ApiError)) {
    return undefined;
  }
  // Widening only: ApiError keeps any code the API sent (client.ts).
  return error.code;
}

/** ADR-008: a 429 carries the wait in seconds as detail.retry_after. */
export function retryAfterOf(error: unknown): number | undefined {
  if (!(error instanceof ApiError) || error.status !== 429) {
    return undefined;
  }
  const seconds = error.detail.retry_after;
  return typeof seconds === "number" && seconds > 0 ? seconds : 1;
}

/** One problem of a 422 validation_failed (P2b, P5a). */
export interface ValidationProblem {
  /** The field: the second entry of loc, after "body". */
  field: string | undefined;
  type: string;
  /** The context values: min_length, place, … */
  context: Record<string, number>;
}

export function validationProblems(error: unknown): ValidationProblem[] {
  if (!(error instanceof ApiError) || error.code !== "validation_failed") {
    return [];
  }
  const errors: unknown = error.detail.errors;
  const list: unknown[] = Array.isArray(errors) ? errors : [];
  return list.flatMap((item) => {
    if (typeof item !== "object" || item === null) {
      return [];
    }
    const entries = Object.entries(item);
    const value = (key: string): unknown =>
      entries.find(([name]) => name === key)?.[1];
    const loc: unknown = value("loc");
    const field: unknown = Array.isArray(loc) ? loc[1] : undefined;
    const type = value("type");
    const context: Record<string, number> = {};
    for (const [key, entry] of entries) {
      if (typeof entry === "number") {
        context[key] = entry;
      }
    }
    return [
      {
        field: typeof field === "string" ? field : undefined,
        type: typeof type === "string" ? type : "",
        context,
      },
    ];
  });
}

/** The business rule a 422 names in its detail, such as "BR-010". */
export function ruleOf(error: unknown): string | undefined {
  if (!(error instanceof ApiError)) {
    return undefined;
  }
  const rule = error.detail.rule;
  return typeof rule === "string" ? rule : undefined;
}
