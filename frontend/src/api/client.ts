// The API client. Paths, parameters and bodies are typed by schema.d.ts,
// which `pnpm generate:api` generates from backend/openapi.json (ADR-008);
// API types are never written by hand.
import createClient, {
  type ClientOptions,
  type Middleware,
} from "openapi-fetch";

import type { components, paths } from "./schema";
import { endSession, getAccessToken, setAccessToken } from "./token";

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

// Routes whose 401 means wrong credentials or a dead refresh token, never
// an expired access token.
const NO_REFRESH = new Set([
  "/api/v1/auth/login",
  "/api/v1/auth/refresh",
  "/api/v1/auth/logout",
]);

// The one refresh in flight for this tab (ADR-006): requests that get 401
// meanwhile wait for it instead of starting their own.
let refreshing: Promise<boolean> | undefined;

function isAccessToken(body: unknown): body is { access_token: string } {
  return (
    typeof body === "object" &&
    body !== null &&
    "access_token" in body &&
    typeof body.access_token === "string"
  );
}

/**
 * Exchanges the refresh cookie for a new access token. The browser sends
 * the cookie itself; the header is the one cross-site forms cannot send
 * (ADR-006). A refused refresh ends the session; a network failure rejects
 * like any other request, and the session stays.
 */
async function refresh(
  baseUrl: string,
  fetchFn: (request: Request) => Promise<Response>,
): Promise<boolean> {
  const response = await fetchFn(
    new Request(`${baseUrl}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    }),
  );
  const body: unknown = response.ok ? await response.json() : undefined;
  if (isAccessToken(body)) {
    setAccessToken(body.access_token);
    return true;
  }
  endSession();
  return false;
}

function refreshOnce(
  baseUrl: string,
  fetchFn: (request: Request) => Promise<Response>,
): Promise<boolean> {
  refreshing ??= refresh(baseUrl, fetchFn).finally(() => {
    refreshing = undefined;
  });
  return refreshing;
}

function withToken(request: Request): Request {
  const token = getAccessToken();
  if (token !== null) {
    request.headers.set("Authorization", `Bearer ${token}`);
  }
  return request;
}

// A copy of each request that may be sent again, by openapi-fetch's id for
// the call: the request that went out has spent its body.
const retries = new Map<string, Request>();

/**
 * Authentication for every call (ADR-006, ADR-008): the access token as
 * `Authorization: Bearer`, and after a 401 one refresh and one retry.
 */
const authMiddleware: Middleware = {
  onRequest({ request, schemaPath, id }) {
    const sent = withToken(request);
    if (!NO_REFRESH.has(schemaPath)) {
      retries.set(id, sent.clone());
    }
    return sent;
  },
  async onResponse({ response, options, id }) {
    const retry = retries.get(id);
    retries.delete(id);
    if (response.status !== 401 || retry === undefined) {
      return undefined;
    }
    if (!(await refreshOnce(options.baseUrl, options.fetch))) {
      return undefined;
    }
    return options.fetch(withToken(retry));
  },
  onError({ id }) {
    retries.delete(id);
  },
};

/** A client typed by `Paths`, with the authentication every call needs. */
export function createApi<Paths extends object = paths>(
  options?: ClientOptions,
) {
  const client = createClient<Paths>({ fetch: globalFetch, ...options });
  client.use(authMiddleware);
  return client;
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
