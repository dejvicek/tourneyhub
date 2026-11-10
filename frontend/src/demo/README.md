# Demo mode

`pnpm dev:demo` (or `VITE_DEMO=true pnpm dev`) runs the app against a fake API: an MSW worker in the browser answers every `/api/v1/…` request from an in-memory store. A reload starts again from the seed. A production build never contains it: `main.tsx` imports `browser.ts` dynamically, behind a `MODE !== "production"` check the bundler removes, and ESLint stops app code from importing anything here except `rules.ts` and `contract.ts`.

| File                 | What it holds                                                                                                  |
| -------------------- | -------------------------------------------------------------------------------------------------------------- |
| `contract.ts`        | Provisional request and response types for routes the backend does not have yet, in openapi-typescript's shape |
| `rules.ts`           | The rules open in issue #24, with their PRD defaults; screens and handlers read them from here                 |
| `seed.ts`            | One league, 16 players, Season 1, two finished tournaments and a DYP running its round robin                   |
| `store.ts`           | The in-memory data and what the backend would compute on read                                                  |
| `engine.ts`          | Stand-ins for schedules, draws, standings and places (`// demo only, the engine decides`)                      |
| `handlers/<area>.ts` | The fake API, one module per area; `allHandlers.ts` lists them                                                 |

The Vitest tests use the same handlers (`src/test/server.ts`).

## Adding a screen

1. Its route and placeholder already exist: find the path in `src/lib/paths.ts` and the page in `src/features/<area>/`. Fill in the page; do not rename it.
2. Put its texts in `src/i18n/locales/en/<area>.ts` and `cs/<area>.ts`.
3. Put its queries and mutations in `src/features/<area>/api.ts`. A route the backend has goes through `api`; a route it does not have yet goes through `provisionalApi`.
4. A route that is new to the demo needs a contract entry in your area's section of `contract.ts` and a handler in `handlers/<area>.ts`, written with `route()` so its body is typed. A write sends the target state (ADR-008).
5. A rule from issue #24 is read from `rules.ts`, never written into the screen.

## Switching an area to the real API

Once the backend serves a route and it is in `backend/openapi.json`:

1. Delete the route, and any type only it used, from `contract.ts`. `pnpm typecheck` then shows every call that still uses the provisional types.
2. In the feature's `api.ts`, change `provisionalApi` to `api` for that route, and take its types from `@/api/schema`.
3. Keep the handler, typed from the generated schema, so the demo and the tests still answer the route; delete it only if the demo should no longer serve it.
