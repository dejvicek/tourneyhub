# CLAUDE.md — TourneyHub Agent Operating Manual

> Read this first, every session. It is the authoritative guide for building TourneyHub with AI coding agents.
> **`PRD.md` governs** product behaviour; **`DATA-MODEL.md`** governs the schema; **`ADR.md`** governs architecture; **`ROADMAP.md`** lists what is deliberately *not* being built yet and the seams reserved for it. If code and a governing doc disagree, fix the code or open a documented change to the doc — never diverge silently.

---

## 1. What this project is

TourneyHub is an open-source, **hosted-first, multi-tenant** platform for running leagues and tournaments for any competitive discipline. Self-hosting uses the same codebase seeded with one default Organization. Every piece of competition data belongs to exactly one **Organization** (tenant); there is no implicit tenant.

## 2. Stack (ADR-003, ADR-011)

| Layer | Choice |
|---|---|
| Backend | **Python 3.13**, **FastAPI** (ASGI, uvicorn), **Pydantic v2** (`extra="forbid"`), **SQLAlchemy 2.0 async** + asyncpg, **Alembic**, pydantic-settings (`TOURNEYHUB_*` env) |
| Data | **PostgreSQL 16** (citext, RLS), **Redis 7** (SSE fan-out, rate limits, cache) |
| Realtime | **Server-Sent Events** (`sse-starlette`) + Redis pub/sub + stream replay (ADR-007) |
| Background | `tourneyhub worker` asyncio process: outbox relay, email sender, timeouts, retention (ADR-010) |
| Auth | Argon2id (argon2-cffi), JWT access (PyJWT) + rotating refresh (ADR-008) |
| API | REST + JSON, OpenAPI 3.1 generated → **committed `api/openapi.json`** with CI drift gate (ADR-005); RFC 7807 errors (`spec/error-catalog.md`) |
| Frontend | **React 19 + Vite + TypeScript (strict)**, Tailwind v4 + `design/tokens.css`, TanStack Query, react-router v7, react-i18next, `openapi-typescript` client, Bruno collection |
| Tests | pytest, pytest-asyncio, hypothesis, testcontainers (Postgres+Redis), Playwright |
| Quality | ruff, mypy `--strict`, import-linter, bandit, pip-audit; ESLint/oxlint, tsc |
| Package mgmt | **uv** (`uv.lock` committed); npm in `/web` |
| Money | Python `int` minor units + `currency`; `Decimal` only for bp→minor with `ROUND_HALF_EVEN`; **never `float`** |

## 3. Repo layout (target)

```
/CLAUDE.md /PRD.md /ROADMAP.md /DATA-MODEL.md /ADR.md /README.md /LICENSE
/api/openapi.json                 # generated, committed, drift-checked
/spec/requirements.yaml           # traceability — UPDATE as you implement
/spec/test-vectors/*.json         # golden oracles (write tests from these)
/spec/error-catalog.md            # stable error codes (append; never rename)
/design/tokens.css                # design tokens for the web app
/src/tourneyhub/
  core/                           # settings, db, tenant session, auth deps, errors, outbox/audit ports,
                                  # registry, ids (uuid7), money, time, splitmix64
  modules/<name>/{domain,application,infrastructure,api,events.py,permissions.py,tests}/
  cli.py                          # `tourneyhub api|worker|openapi export|seed|bootstrap`
/migrations/                      # alembic (single history)
/tests/{unit,integration,contract,e2e}/
/web/                             # React app (see /web/README.md once scaffolded)
/docker-compose.yml /.env.example /Dockerfile
```

Module DAG (ADR-004): `platform` ← `identity` ← `invitations`; `platform, identity` ← `leagues` ← `tournaments` ← `finance`; `platform` ← `realtime`. Cross-module imports only via `modules/<other>/application/public.py`. import-linter enforces this.

## 4. Commands

> Keep this table current once the scaffold exists; agents rely on it.

| Task | Command |
|---|---|
| Install | `uv sync` · `cd web && npm ci` |
| Infra | `docker compose up -d` (Postgres, Redis, Mailpit) |
| API dev | `uv run tourneyhub api --reload` (→ http://localhost:8000, docs at `/docs`) |
| Worker | `uv run tourneyhub worker` |
| Migrations | `uv run alembic revision -m "<slice>"` (hand-review) · `uv run alembic upgrade head` · `uv run alembic check` |
| Tests | `uv run pytest` · `uv run pytest tests/integration` (needs Docker) · `uv run pytest -m property` |
| Lint / types / boundaries | `uv run ruff check . && uv run ruff format --check .` · `uv run mypy` · `uv run lint-imports` |
| Security | `uv run bandit -r src` · `uv run pip-audit` |
| OpenAPI | `uv run tourneyhub openapi export` (writes `api/openapi.json`) · CI: `--check` |
| Web | `npm run dev` · `npm run typecheck` · `npm run lint` · `npm run build` · `npm run gen:api` · `npm run gen:bruno` / `gen:bruno:check` · `npx playwright test` |
| Self-host bootstrap | `uv run tourneyhub bootstrap` (seeds default org + env admin, FR-009a/FR-150) |

## 5. Gates

- **G1 — Data model approved.** While `DATA-MODEL.md` says `DRAFT`, you may build: scaffold, tooling, CI, `core/` kernel without DB, pure domain code (formats, scoring, money, splitmix64) against `spec/test-vectors/`, and the web shell. You may **not** write SQLAlchemy models, Alembic migrations, repositories, or persisting endpoints (ADR-012). Any later schema change must edit `DATA-MODEL.md` in the same PR.
- **G2 — Contract.** Any API change ships with the regenerated `api/openapi.json` and regenerated web types/Bruno collection.
- **G3 — Isolation.** Any new tenant-scoped table/endpoint/channel/job ships with a two-org isolation test and an RLS policy in its migration.

## 6. HARD GUARDRAILS (violating these fails review)

1. **Tenancy.** Non-null immutable `organization_id` on every tenant-scoped table; org resolved **server-side** (URL + membership), never from body/query; every query through the `TenantSession`; RLS `SET LOCAL app.current_org_id`; SSE channels and Redis keys prefixed `org:{id}`. Cross-org access is a P0 defect. (NFR-004/024, FR-151/152/154, ADR-006)
2. **Money.** `bigint` minor units + `char(3)` currency; `int` math; banker's rounding for bp splits with residual to top rank; team split floor + remainder to captain. Verify against `spec/test-vectors/payout-split.json`. `float` is banned in `finance` and competition math (BR-008, FR-081).
3. **Determinism.** Bracket generation, seeding, ranking and tie-breaks are pure functions of inputs + stored `rng_seed` (splitmix64, ADR-002 §2.4). No `random`, `time`, `datetime.now`, `uuid4` in those packages. Verify against `spec/test-vectors/`. (NFR-018)
4. **Server authoritative.** Results, standings, payouts computed server-side inside the write transaction (ADR-002); clients only render optimistic state for their own action.
5. **Concurrency.** `version` column on mutable aggregates; `If-Match` required on mutations (428 if missing) → 409 `concurrency_conflict`; domain guards return 422 with a catalog code. (NFR-023)
6. **Time.** `timestamptz` UTC only; `datetime` objects always tz-aware; localise in the UI. (NFR-022)
7. **Types.** `mypy --strict` clean; no `# type: ignore` without an issue link; no `Any` in public signatures; TS strict, no `as any`/`@ts-ignore`.
8. **Secrets & PII.** Env config only; structlog scrubber; never log tokens, passwords, emails in full, or request bodies of auth/finance routes. (NFR-021)
9. **Errors.** RFC 7807 with a stable `code` from `spec/error-catalog.md` (append new codes there first). Never `except: pass`.
10. **Auth gates.** Verified email before organizing/money (403 `email_not_verified`); capability check + object-level ownership on every read/write; cross-org ids → 404.
11. **Boundaries.** Domain packages import no framework/IO; modules import each other only via `application/public.py`; new plugins register via `ModuleManifest`, never via `if format_type == ...` in core.
12. **Audit.** Security, finance, admin and result-override mutations append an audit row in the same transaction with before/after.

## 7. How to add a module (the recipe — ADR-004, `ROADMAP.md`)

1. Read the module brief in `ROADMAP.md` §2 and the seams in §3. Confirm its `depends_on` keeps the DAG acyclic.
2. Add its requirements to `PRD.md` (promote the IDs listed in `ROADMAP.md` §4) and its tables to `DATA-MODEL.md`; get G1 approval for the delta.
3. `mkdir src/tourneyhub/modules/<name>/{domain,application,infrastructure,api,tests}`; create `__init__.py` exporting `module = ModuleManifest(name=..., depends_on=(...), routers=(...), models=(...), event_handlers=(...), permissions=(...), format_plugins=..., payment_providers=..., notification_channels=..., scheduled_jobs=...)`.
4. Register it in `core/registry.py` built-in list (or via entry point for external plugins). Add an import-linter contract for the new package.
5. Write the failing tests: domain unit tests (+ golden vectors if it computes anything), state-machine table, isolation test, contract snapshot.
6. Additive Alembic migration only (new tables/columns/CHECK widening; RLS policy for tenant tables). Never repurpose an existing column.
7. Implement; export OpenAPI; regenerate web types; wire UI behind the module's capability keys.
8. Update `spec/requirements.yaml`, `README.md` command table if needed, and `ROADMAP.md` (mark the module as promoted).

## 8. How to work a slice (the loop)

1. Pick **one** slice from `PRD.md` §22 (respect milestone order and gates). Read its FR/NFR/BR lines and any `spec/test-vectors/` it references.
2. Write the failing tests first (domain → integration → contract).
3. Implement the minimum; respect §6 and module boundaries.
4. Verify: ruff, mypy, import-linter, pytest (unit + integration), `alembic check`, OpenAPI drift, web typecheck/lint/build if touched.
5. Update `spec/requirements.yaml` (`status`, `files`, `tests`) for every FR touched.
6. Commit (§10). One concern per commit; if a slice needs more than a handful of files, split it.

## 9. Definition of Done (per slice)

- [ ] ruff + mypy strict + import-linter + bandit clean
- [ ] `pytest` green incl. integration on real Postgres/Redis
- [ ] Migration applies from empty DB; `alembic check` clean; RLS policy present for new tenant tables
- [ ] `api/openapi.json` regenerated and committed; web types/Bruno regenerated if API changed
- [ ] Two-org isolation test for any new tenant-scoped surface
- [ ] Relevant `spec/test-vectors/` cases covered
- [ ] Web `typecheck` + `lint` + `build` clean if touched
- [ ] `spec/requirements.yaml` updated
- [ ] No §6 guardrail violated
- [ ] `DATA-MODEL.md` updated if the schema changed

**No evidence = not done.**

## 10. Commit & PR conventions

- Conventional Commits + leading gitmoji, FR/NFR IDs in subject or body:
  `✨ feat(tournaments): single-elimination generation (FR-047, FR-053)` · `🐛 fix(finance): remainder to captain (FR-075a)` · `📝 docs:` · `♻️ refactor:` · `✅ test:` · `🔧 chore:` · `🗃️ db:` (migrations)
- Author = the repo owner only. **Never add AI/assistant attribution, `Co-authored-by`, or "generated by" trailers.**
- Never commit `.env`, secrets, `node_modules`, build output. Commit `uv.lock` and `package-lock.json`.
- Branch naming: `feat/<module>-<slice>`, `fix/<module>-<issue>`.

## 11. Pointers

- Requirements → `PRD.md` (§6 FRs, §7 NFRs, §8 BRs, §10 state machines, §11 permissions, §12 formats/scoring, §22 sequencing).
- Not-yet features and reserved seams → `ROADMAP.md`.
- Schema, RLS, conventions → `DATA-MODEL.md`.
- Decisions and semantics (recompute, concurrency, outbox, PRNG, tenancy, SSE, auth) → `ADR.md`.
- Error codes → `spec/error-catalog.md`. Oracles → `spec/test-vectors/`. Coverage → `spec/requirements.yaml`.
