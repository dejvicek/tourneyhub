// The provisional API contract: request and response types for the routes the
// backend does not have yet, written in the shape that openapi-typescript
// generates, so that openapi-fetch types calls to them. It is a stand-in and
// may change freely. When the backend adds a route, the generated
// src/api/schema.d.ts types it: delete it here, and the screen's api.ts
// switches from provisionalApi to api (src/test/fake/README.md).
//
// Names follow the API's conventions (ADR-008, DATA-MODEL.md): /api/v1,
// snake_case, UUIDs, enumerations as string literals.
import type { LateEntryWrite } from "@/api/provisionalTypes";
import type { components, paths as GeneratedPaths } from "@/api/schema";

type Uuid = string;

type ErrorResponse = components["schemas"]["ErrorResponse"];
type ParticipantRead = components["schemas"]["ParticipantRead"];

/** Never in the backend: the seeded account the login shows in demo mode. */
export interface DemoAccount {
  email: string;
  password: string;
  signup_code: string;
}

interface Json<T> {
  headers: Record<string, unknown>;
  content: { "application/json": T };
}
interface Errors {
  default: Json<ErrorResponse>;
}
interface NoParams {
  query?: never;
  header?: never;
  path?: never;
  cookie?: never;
}
interface Params<P> {
  query?: never;
  header?: never;
  path: P;
  cookie?: never;
}
interface Get<P, R> {
  parameters: P;
  requestBody?: never;
  responses: { 200: Json<R> } & Errors;
}
interface Post<P, B, R> {
  parameters: P;
  requestBody: { content: { "application/json": B } };
  responses: { 201: Json<R> } & Errors;
}
type Tournament = Params<{ league_id: Uuid; tournament_id: Uuid }>;

/** Routes the fake API serves that the generated schema does not have yet. */
export interface ProvisionalPaths {
  // public: every share-link route is generated (P11, P10a, P10b, P12).

  // demo only: the backend never has this route
  "/api/v1/demo/account": { get: Get<NoParams, DemoAccount> };

  // finals: late players
  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/entries": {
    post: Post<Tournament, LateEntryWrite, ParticipantRead>;
  };
}

/**
 * The generated paths plus the provisional ones. A path in both keeps its
 * generated methods and gains the provisional ones; a method in both would
 * be a contract error, so delete it here once the backend has it.
 */
type MergePaths<A, B> = {
  [K in keyof A | keyof B]: K extends keyof B
    ? K extends keyof A
      ? Omit<A[K], keyof B[K]> & B[K]
      : B[K]
    : K extends keyof A
      ? A[K]
      : never;
};

/** The HTTP methods a path item defines: openapi-typescript writes `get?: never` for the others. */
type DefinedMethods<T> = {
  [K in keyof T]-?: K extends "parameters"
    ? never
    : [Exclude<T[K], undefined>] extends [never]
      ? never
      : K;
}[keyof T];

/** "path method" for each method that both the contract and the generated schema define. */
type Contract = ProvisionalPaths;
type Duplicates = {
  [P in keyof Contract & keyof GeneratedPaths]: `${P} ${DefinedMethods<
    Contract[P]
  > &
    DefinedMethods<GeneratedPaths[P]> &
    string}`;
}[keyof Contract & keyof GeneratedPaths];

/**
 * Fails `pnpm typecheck` once the backend serves a route the contract still
 * declares; the error names it as "path method". Delete it here
 * (src/test/fake/README.md, "Switching an area to the real API").
 */
type NoDuplicates<T extends never> = T;
export type ContractDuplicates = NoDuplicates<Duplicates>;

export type ProvisionalApiPaths = MergePaths<GeneratedPaths, ProvisionalPaths>;
