// The API client. Paths, parameters and bodies are typed by schema.d.ts,
// which `pnpm generate:api` generates from backend/openapi.json (ADR-008);
// API types are never written by hand.
import createClient, { type ClientOptions } from "openapi-fetch";

import type { components, paths } from "./schema";

export type ErrorResponse = components["schemas"]["ErrorResponse"];
export type ErrorCode = ErrorResponse["code"];

/** A call that did not succeed, with the API's stable error code (ADR-008). */
export class ApiError extends Error {
  readonly status: number;
  /** Undefined when the body is not the API's error shape, e.g. a proxy error page. */
  readonly code: ErrorCode | undefined;
  readonly detail: ErrorResponse["detail"];

  constructor(status: number, body: unknown) {
    const error = isErrorResponse(body) ? body : undefined;
    super(`API call failed with ${String(status)} ${error?.code ?? ""}`.trim());
    this.name = "ApiError";
    this.status = status;
    this.code = error?.code;
    this.detail = error?.detail ?? {};
  }
}

// Query and mutation errors are ApiErrors: every call goes through dataOf.
// A network failure still arrives as a TypeError, so code that tells the
// two apart checks `instanceof ApiError` (docs/frontend-style.md §8.1).
declare module "@tanstack/react-query" {
  interface Register {
    defaultError: ApiError;
  }
}

/**
 * Looks up the global fetch on every call; openapi-fetch would keep the one
 * it found when the client was created, which MSW in the tests replaces
 * later.
 */
export function globalFetch(request: Request): Promise<Response> {
  return fetch(request);
}

export function createApi(options?: ClientOptions) {
  return createClient<paths>({ fetch: globalFetch, ...options });
}

/** The API on the page's own origin: Vite's proxy in development, Caddy in production (ADR-005). */
export const api = createApi();

interface CallResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/**
 * The data of a successful call; rejects with an ApiError otherwise, so it
 * can serve as a TanStack Query `queryFn` or `mutationFn`.
 */
export async function dataOf<T>(call: Promise<CallResult<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) {
    throw new ApiError(response.status, error);
  }
  // openapi-fetch returns the success member of its result union for a 2xx.
  return data as T;
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    typeof value.code === "string" &&
    "detail" in value &&
    typeof value.detail === "object" &&
    value.detail !== null
  );
}
