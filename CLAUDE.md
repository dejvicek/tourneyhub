# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

TourneyHub keeps long-term statistics for leagues of game nights (table football first, any sport or game later). A **league** runs in **seasons**; each season holds 1–N **tournaments**, and every tournament can use a different format. Season standings and the league ranking are built from tournament places, so every tournament's outcome feeds the long-term statistics.

Tournament formats combine a **type** (Singles, Doubles, DYP, Monster DYP) with an optional **group phase** (round robin, Swiss or Monster DYP rounds) and an optional single-elimination **knockout**.

- Singles, Doubles, round robin, Swiss and the knockout are meant to be **as fair as possible** for the players: seeding by league ranking, tie-breakers (round robin: head-to-head between two level entries, then game difference, then score difference; Swiss and Monster DYP: BH1, BH2 and score difference in the organizer's order), no repeat opponents while that can be avoided.
- **DYP** ("Draw Your Partner") and **Monster DYP** lean towards **casual players**: partners are drawn (top half + bottom half in DYP, new teams every round in Monster DYP), so weaker players play with stronger ones. Keep that intent when changing their rules: mixing players matters more there than strict fairness.

## Ownership

This codebase is yours: what it's for and how it's built are your call, and you'll keep building on it.

## Where the decisions live

All documents live in `docs/` (index: `docs/README.md`). Read the relevant one before changing behaviour; code must follow them, and changes to rules go through them.

| Document | Holds |
|---|---|
| `docs/product/PRD.md` | What the MVP does. Requirement IDs `FR-xxx`, business rules `BR-xxx`, glossary (§3). The user owns it. |
| `docs/product/MVP-ROADMAP.md` | What is left before the MVP (packages P1–P16, follow-ups, demo removal), as a checklist mirroring issue #84. |
| `docs/product/ROADMAP.md` | Post-MVP items (`RM-xx`). Not in scope unless moved into the PRD. |
| `docs/architecture/ADR.md` | How it is built (ADR-001 – ADR-014). |
| `docs/architecture/DATA-MODEL.md` | Tables, constraints, what the DB enforces vs. the app (§5). |
| `docs/architecture/diagrams/` | LikeC4 model; validate with `npx likec4@1.60.0 validate docs/architecture/diagrams`. |
| `docs/style/python-style.md` | Backend rules. Load the `python-style` skill before touching `backend/`. |
| `docs/style/frontend-style.md` | Frontend rules. Load the `frontend-style` skill before touching `frontend/`. |

New documents go into the matching folder and get a row in `docs/README.md`.

### Keeping the MVP roadmap current

Issue [#84](https://github.com/dejvicek/tourneyhub/issues/84) is the MVP checklist; `docs/product/MVP-ROADMAP.md` mirrors it item for item. Keep the two identical:

- A PR that finishes a checklist item ticks it in `MVP-ROADMAP.md` in the same PR and adds the PR link, e.g. `([#57](…/pull/57))`. Once the PR is merged, tick the same item in issue #84 (`gh issue edit 84 --body-file …`).
- When the plan changes (a new follow-up issue, a split or dropped item, an open question answered), change both the file and the issue body the same way.
- A parent item is ticked only when all its sub-items are. A finished package moves to section 1 "Done".
- If the file and the issue disagree, the issue wins; fix the file to match.

Code and tests that implement a rule cite its ID (`BR-056`, `FR-082`) in a docstring, comment or test name.

## Architecture

Monorepo: `backend/` (Python 3.15, FastAPI, SQLAlchemy 2.1, Alembic, PostgreSQL 17), `frontend/` (React 19, Vite, TypeScript, Tailwind, shadcn/ui, TanStack Query), Caddy serving both on one origin in production (ADR-005).

### Backend layers (`backend/src/tourneyhub/`, enforced by import-linter)

`api` and `cli` → `services` → `db` → `engine`. Imports only go downwards.

- **`engine/`**: the tournament rules as pure functions over immutable data classes (ADR-009): seeding, DYP draws, schedules, Swiss and Monster DYP pairing, standings, places, season points, fields. No DB, no framework, no clock, no randomness. Needs 100 % coverage. Also holds the domain `StrEnum`s.
- **`services/<area>.py`**: use cases as module-level functions (`generate_round(session, *, …)`). Take locks, check state, call the engine, raise `AppError`s. Never commit, never import FastAPI.
- **`api/<area>.py`**: routers that turn requests into service calls and results into response models. No queries of their own.
- **`db/models/`**: one module per DATA-MODEL §4 area. Migrations live in `tourneyhub/migrations` (run with `tourneyhub migrate`).

Key cross-cutting decisions:
- **Derived data is computed on read** (ADR-009): standings, tie-breakers, places, season standings and the league ranking are never stored; the app loads stored facts and calls the engine. Corrections therefore need no recalculation. Stored: organizer decisions, draws, rounds, matches, results, per-round participation, field assignments.
- **Lots are deterministic** (ADR-010): each tournament has a stored 128-bit seed; a lot orders candidates by `SHA-256(seed ‖ purpose ‖ id)`. Python's `random` is banned everywhere. Draws are stored and never silently re-drawn.
- **Pairing fallbacks** (ADR-011): Swiss uses BR-056 first and a minimum-weight matching (`engine/matching.py`, networkx) when stuck; Monster DYP uses swaps, then the matching.

### API contract

REST under `/api/v1`; share-link views are anonymous under `/api/v1/public/{share_token}/…` (ADR-008). `backend/openapi.json` is exported by `python -m tourneyhub.openapi`, committed and checked for drift. The frontend generates `src/api/schema.d.ts` from it (`pnpm generate:api`, git-ignored, run automatically by most scripts). **After changing an API route or model, regenerate `backend/openapi.json` and commit it.**

### Frontend (`frontend/src/`)

Imports flow one way (ESLint-enforced): `api`, `i18n`, `components`, `hooks`, `lib` → `features/<area>/` → `pages`, `routes.tsx`, `App.tsx`, `main.tsx`. All HTTP goes through the openapi-fetch client in `src/api/client.ts`; types come only from the generated schema. UI text in English and Czech (`src/i18n/locales/{en,cs}/`). Demo mode (`pnpm dev:demo`, `src/demo/`) runs every screen against the fake API in `src/test/fake/` (MSW), which the Vitest suite also uses; routes the backend lacks go through `provisionalApi`.

## Commands

Copy `.env.example` to `.env` first. Dev and prod stacks share the Compose project and DB volume: `docker compose down` one before starting the other.

```sh
docker compose up --build        # dev: db, api (reload, migrates on start) on :8000, frontend (Vite) on :5173
docker compose -f compose.yaml -f compose.prod.yaml up --build --detach --wait   # prod stack on https://localhost:8443
```

### Backend (inside the dev `api` container; `uv run` does not work there)

Tests need two empty databases, created once per volume:

```sh
docker compose exec db createdb -U postgres tourneyhub_test
docker compose exec db createdb -U postgres tourneyhub_test_migrations
```

Full check, as in CI:

```sh
docker compose exec api sh -c '
  db=${TOURNEYHUB_DATABASE_URL%/*}
  export TOURNEYHUB_TEST_DATABASE_URL=$db/tourneyhub_test
  export TOURNEYHUB_TEST_MIGRATIONS_DATABASE_URL=$db/tourneyhub_test_migrations
  ruff format --check && ruff check && mypy && lint-imports &&
  coverage run -m pytest && coverage report &&
  coverage report --include="*/tourneyhub/engine/*" --fail-under=100 &&
  python -W error -m tourneyhub.openapi | diff -u openapi.json -'
```

Single test: `docker compose exec api pytest tests/engine/test_swiss.py -k br057` (test names carry the rule ID). Engine tests need no database; tests that touch one need the two exports above. `pytest -m benchmark` runs the timing benchmarks skipped by default. pytest-randomly shuffles the order, and warnings are errors.

Regenerate the schema after API changes: `docker compose exec api sh -c 'python -W error -m tourneyhub.openapi > openapi.json'`.

On the host with uv instead (needs your own PostgreSQL 17): see `docs/style/python-style.md` §2, run from `backend/`.

### Frontend (from `frontend/`; Node 26.13.0, pnpm 12.18.0)

```sh
pnpm install --frozen-lockfile
pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build
pnpm exec vitest run src/routes.test.tsx -t "name"   # single test (run pnpm generate:api first if the schema is stale)
pnpm dev:demo                                        # every screen against the fake API
```

Inside Docker: `docker compose exec frontend pnpm lint`.

### End-to-end (Playwright, against the prod stack)

With `HTTP_PORT=8080` and `HTTPS_PORT=8443` in `.env` and the prod stack up: `cd frontend && pnpm e2e` (single spec: `pnpm e2e -g "name"`). `pnpm exec playwright install chromium` once.

## Keep changes proportional

- Don't add ADR history, extra CI checks or rewordings of business rules unless asked.
- If a BR-xxx rule rewording changes meaning or gets longer, show before/after and ask first.

## Git workflow

- **Conventional Commits with a gitmoji prefix**, matching the history: `✨ feat(engine): …`, `🐛 fix(frontend): …`, `✅ test(e2e): …`, `📝 docs(adr): …`, `🔧 chore: …`, `👷 ci: …`, `♻️ refactor(…): …`. Scopes are areas such as `engine`, `tournaments`, `leagues`, `auth`, `public`, `frontend`, `backend`, `product`, `architecture`, `style`. Moves and renames use 🚚.
- **Many small commits over one large commit.** Split work into focused, self-contained commits (e.g. engine rule + its tests, then the service, then the route and `openapi.json`, then the screen) rather than one commit per feature.
- Work on a branch and open a PR to `main`; CI (`.github/workflows/ci.yml`) runs backend, frontend and e2e jobs only for changed areas, and `ci-ok` is the required check.