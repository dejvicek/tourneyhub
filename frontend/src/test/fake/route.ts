// Typed MSW handlers for the demo's fake API. A handler names its route as
// the contract does ("/api/v1/leagues/{league_id}"), gets the path
// parameters and the body typed from it, and returns the success body the
// contract declares, or a Response made by apiError().
import { http, HttpResponse, type JsonBodyType } from "msw";

import type { paths } from "@/api/schema";

import type { ErrorResponse } from "./contract";

type Method = "get" | "post" | "put" | "patch" | "delete";

type PathsWith<M extends Method> = {
  [P in keyof paths]: paths[P] extends Record<M, unknown> ? P : never;
}[keyof paths];

type Operation<P extends keyof paths, M extends Method> =
  paths[P] extends Record<M, infer O> ? O : never;

type PathParams<O> = O extends { parameters: { path: infer X } }
  ? X
  : Record<string, never>;

type RequestBody<O> = O extends {
  requestBody: { content: { "application/json": infer B } };
}
  ? B
  : undefined;

interface JsonContent<T> {
  content: { "application/json": T };
}
type SuccessBody<O> = O extends { responses: infer R }
  ? R extends { 200: JsonContent<infer D> }
    ? D
    : R extends { 201: JsonContent<infer D> }
      ? D
      : null
  : never;

interface ResolverInput<O> {
  params: PathParams<O>;
  body: RequestBody<O>;
  url: URL;
}

type Resolver<O> = (
  input: ResolverInput<O>,
) => SuccessBody<O> | Response | Promise<SuccessBody<O> | Response>;

/** "/api/v1/leagues/{league_id}" → "/api/v1/leagues/:league_id" for MSW. */
function mswPath(path: string): string {
  return path.replace(/\{(\w+)\}/g, ":$1");
}

/**
 * A handler for one route of the contract. The status of a success is 200,
 * or `status` (201 for a create); a resolver that returns null answers 204.
 */
export function route<M extends Method, P extends PathsWith<M>>(
  method: M,
  path: P,
  resolve: Resolver<Operation<P, M>>,
  status: 200 | 201 = 200,
) {
  return http[method](mswPath(path), async ({ request, params }) => {
    const hasBody = ["POST", "PUT", "PATCH"].includes(request.method);
    // A POST may carry no body at all, such as a generate.
    const text = hasBody ? await request.text() : "";
    const result: unknown = await resolve({
      // MSW parses the parameters the contract names from the same path.
      params: params as PathParams<Operation<P, M>>,
      // demo only: the fake API trusts its typed caller and validates nothing.
      body: (text === "" ? undefined : JSON.parse(text)) as RequestBody<
        Operation<P, M>
      >,
      url: new URL(request.url),
    });
    if (result instanceof Response) {
      return result;
    }
    if (result === null) {
      return new HttpResponse(null, { status: 204 });
    }
    // The contract's bodies are plain JSON data.
    return HttpResponse.json(result as JsonBodyType, { status });
  });
}

/** An error in the API's shape (ADR-008). */
export function apiError(
  status: number,
  code: ErrorResponse["code"],
  detail: ErrorResponse["detail"] = {},
): Response {
  return HttpResponse.json({ code, detail } satisfies ErrorResponse, {
    status,
  });
}
