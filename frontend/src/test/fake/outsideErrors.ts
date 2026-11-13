// Errors of the outside group's handlers: the API's shape (ADR-008) with
// optional headers and the validation_failed problem list.
import { HttpResponse } from "msw";

import type { ErrorResponse } from "./contract";

export function outsideError(
  status: number,
  code: ErrorResponse["code"],
  detail: ErrorResponse["detail"] = {},
  headers: Record<string, string> = {},
): Response {
  return HttpResponse.json({ code, detail }, { status, headers });
}

/** One problem of a 422 `validation_failed`, as FastAPI reports it (P2b). */
export interface Problem {
  loc: (string | number)[];
  type: string;
  [context: string]: string | number | (string | number)[];
}

export function validationFailed(problems: Problem[]): Response {
  return outsideError(422, "validation_failed", { errors: problems });
}

/** P2b and P5a strip names and require 1 to 100 characters. */
export function nameProblem(
  value: string,
  loc: (string | number)[],
): Problem | undefined {
  const name = value.trim();
  if (name.length === 0) {
    return { loc, type: "string_too_short", min_length: 1 };
  }
  if (name.length > 100) {
    return { loc, type: "string_too_long", max_length: 100 };
  }
  return undefined;
}
