# Demo mode

`pnpm dev:demo` (or `VITE_DEMO=true pnpm dev`) runs the app against a fake API: an MSW worker in the browser answers every `/api/v1/…` request from an in-memory store. A reload starts again from the seed. A production build never contains it: `main.tsx` imports `browser.ts` dynamically, behind a `MODE !== "production"` check the bundler removes, and ESLint stops app code from importing anything here or from `src/test`.

The fake API is not in this folder. The tests own it in `src/test/fake/`; the Vitest suite serves it through `src/test/server.ts`. This folder only boots the same handlers in the browser (`browser.ts`). ESLint stops tests and `src/test` from importing anything from `src/demo`.

Everything below is in `src/test/fake/`:

| File                 | What it holds                                                                                                                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `contract.ts`        | Short names for the API types the fake API and its tests use; the provisional paths are in `src/api/provisionalPaths.ts`, the hand-written types the screens use in `src/api/provisionalTypes.ts` |
| `ids.ts`             | `testId()` and each area's id range                                                                                                                                                               |
| `seed.ts`            | One league, 16 players, Season 1, two finished tournaments and a DYP running its round robin                                                                                                      |
| `seedParts.ts`       | The screen areas' own seed files, which `seed.ts` applies after its own data                                                                                                                      |
| `store.ts`           | The in-memory data and what the backend would compute on read                                                                                                                                     |
| `engine.ts`          | Stand-ins for schedules, draws, standings and places (`// demo only, the engine decides`)                                                                                                         |
| `handlers/<area>.ts` | The fake API, one module per area; `allHandlers.ts` lists them                                                                                                                                    |

## Adding a screen

1. Its route and placeholder already exist: find the path in `src/lib/paths.ts` and the page in `src/features/<area>/`. Fill in the page; do not rename it. An overlay (6c, 6d, 7, 7b) is a nested route: its page renders `ResponsiveSheet`, and its parent screen keeps its `<Outlet />`.
2. Put its texts in `src/i18n/locales/en/<area>.ts` and `cs/<area>.ts`.
3. Put its queries and mutations in `src/features/<area>/api.ts`. A route the backend has goes through `api`; a route it does not have yet goes through `provisionalApi`.
4. A route that is new to the fake API needs an entry in `ProvisionalPaths` in `src/api/provisionalPaths.ts` and a handler in `src/test/fake/handlers/<area>.ts`, written with `route()` so its body is typed. A write sends the target state (ADR-008).
5. A rule from issue #24 is read from `src/lib/rules.ts`, never written into the screen.
6. Data the screen needs goes in your area's seed file, never in `seed.ts`: `seedSetup.ts`, `seedPlay.ts`, `seedFinals.ts` or `seedOutside.ts`. It exports a `SeedPart`, and one line in `seedParts.ts` registers it. Its ids come from the kit's `id(n)` or `tournament(base, …)`, within the area's range: the foundation 1–999, setup 1000–1999, play 2000–2999, finals 3000–3999, outside 4000–4999; `testId(n, area)` throws outside it. The file imports only types from `seed.ts` and takes the rest from the kit.

```ts
// src/test/fake/seedFinals.ts
import type { SeedPart } from "./seed";

export const seedFinals: SeedPart = {
  area: "finals",
  add(state, kit) {
    const t = kit.tournament(3000, {
      name: "Monster DYP",
      date: kit.today,
      type: "monster_dyp",
      state: "in_progress",
    });
    // … t.phase(), t.entry(), t.round(), kit.play() …
    state.tournaments.push(t.tournament);
  },
};

// src/test/fake/seedParts.ts
import { seedFinals } from "./seedFinals";
export const seedParts: SeedPart[] = [seedFinals];
```

## Switching an area to the real API

Once the backend serves a route and it is in `backend/openapi.json`:

1. Delete the route from `src/api/provisionalPaths.ts`, and any type only it used from `src/api/provisionalTypes.ts`. `pnpm typecheck` then shows every call that still uses the provisional types.
2. In the feature's `api.ts`, change `provisionalApi` to `api` for that route, and take its types from `@/api/schema`.
3. Keep the handler, typed from the generated schema, so the demo and the tests still answer the route.
