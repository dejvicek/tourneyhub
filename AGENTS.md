# AGENTS.md — TourneyHub Agent Operating Manual

> Read this first, every session. It is the authoritative guide for building TourneyHub with AI coding agents.
> The product spec is [`PRD.md`](./PRD.md); the resolved decisions are [`DECISIONS.md`](./DECISIONS.md).
> **`PRD.md` governs.** If code and PRD disagree, either fix the code or open a documented change to the PRD — never silently diverge.

---

## 1. What this project is

TourneyHub is an open-source, **hosted-first, multi-tenant** platform for running leagues and tournaments for any competitive discipline. Self-hosting is fully supported from the same codebase (seeded with one default Organization). See `PRD.md` §1.

**Non-negotiable framing:** every piece of competition data belongs to exactly one **Organization** (tenant). There is no "implicit tenant" (A-002, NFR-004).

---

## 2. Stack (confirmed — PRD §21, Q-004)

| Layer | Choice |
|---|---|
| Backend | C# / **.NET 8**, ASP.NET Core (modular / clean-architecture or vertical slices) |
| API | **REST + JSON only** (OpenAPI 3). No GraphQL (Q-003). Source of truth: [`api/openapi.yaml`](./api/openapi.yaml) |
| DB | **PostgreSQL** + **EF Core** (migrations; raw SQL escape hatch for heavy stats) |
| Realtime | **SignalR** (WebSocket + fallback), **Redis** backplane |
| Cache/Backplane | **Redis** |
| Frontend | **React + Vite + TypeScript** (SPA); public pages prerendered/SSG for SEO |
| Styling | Tailwind + CSS variables (design tokens — reuse those in `index.html`) |
| Auth | ASP.NET Core Identity (Argon2id/PBKDF2) |
| Testing | **xUnit** (unit) + **Testcontainers** (integration) + **Playwright** (e2e) + **FsCheck** (property-based) |
| Money type | .NET `decimal` for compute; **persist integer minor units + currency** — never `double`/`float` |

---

## 3. Proposed repo layout

```
/PRD.md                     # authoritative product spec
/DECISIONS.md               # resolved decision log
/AGENTS.md                  # this file
/api/openapi.yaml           # API contract (author BEFORE controllers; codegen both sides)
/spec/
  requirements.yaml         # FR/NFR traceability index — UPDATE as you implement
  test-vectors/             # golden input→output oracles (write tests from these)
/src/                       # .NET solution (to scaffold)
  TourneyHub.Domain/        # entities, value objects, domain services (pure)
  TourneyHub.Application/   # use cases, ports (interfaces)
  TourneyHub.Infrastructure/# EF Core, Redis, email, payment providers
  TourneyHub.Api/           # ASP.NET Core host, controllers, SignalR hubs
  modules: Identity | Competition | Finance | Platform  (see PRD §9.3)
/web/                       # React + Vite + TS app (to scaffold)
/tests/                     # unit / integration / e2e
/docker-compose.yml         # Postgres + Redis + Mailpit (to add)
/.env.example               # all config keys (to add)
```

Module boundaries are enforced (NFR-001): **no circular deps**; domain code has no framework/infra dependencies.

---

## 4. Build / test / run commands

> Scaffold not created yet. When it is, keep this table current — agents rely on it as the source of runnable commands.

| Task | Command (placeholder until scaffolded) |
|---|---|
| Backend build | `dotnet build` |
| Backend unit+integration tests | `dotnet test` |
| Start infra (Postgres/Redis/Mail) | `docker compose up -d` |
| EF migrations | `dotnet ef migrations add <Name>` / `dotnet ef database update` |
| Frontend install/dev | `npm ci && npm run dev` (in `/web`) |
| Frontend build / typecheck / lint | `npm run build` / `npm run typecheck` / `npm run lint` |
| Frontend e2e | `npx playwright test` |
| Regenerate TS API client | `npm run gen:api` (from `api/openapi.yaml`) |
| Regenerate Bruno collection | `npm run gen:bruno` (in `/web`) |
| Check Bruno collection is in sync | `npm run gen:bruno:check` (in `/web`) |
| Validate OpenAPI | `npx @redocly/cli lint api/openapi.yaml` |

---

## 5. HARD GUARDRAILS (violating these fails review)

These are the invariants AI most often breaks. They are backed by tests where possible (§8).

1. **Tenancy — non-null `organization_id` everywhere.** Every tenant-scoped entity, query, API call, SignalR group, background job, export, and cache key resolves an Organization **server-side** (never from client input). Cross-org access is a **P0 defect**. (NFR-004, NFR-024, FR-151/152, BR-012/015)
2. **Money — integer minor units only.** Persist `amount_minor` (int/long) + `currency`. Never `double`/`float`. Splits use the rules in `spec/test-vectors/payout-split.json` (banker's rounding for rank distribution → remainder to top rank; team split equal → remainder to captain). (BR-008, FR-081, FR-075a)
3. **Determinism.** Bracket generation, seeding, and ranking are deterministic given inputs + a **stored `rng_seed`**. No wall-clock/`Random.Shared` in these paths. Verify against `spec/test-vectors/`. (NFR-018, FR-047)
4. **Server is authoritative** for results; clients may render optimistic UI but reconcile to server state. (FR-062, BR-010)
5. **Concurrency.** Mutable competition/finance entities carry a `version`; updates use optimistic locking (ETag/`If-Match` → 409 on conflict). (NFR-023)
6. **Time.** Store UTC (ISO-8601). Localize only at presentation. Never store naive local time. (NFR-022)
7. **No type-safety suppression.** No `as any`, `@ts-ignore`, `@ts-expect-error`, or C# `!`-abuse/`#pragma warning disable` to hide real issues.
8. **No secrets in code/logs.** Env-based config; never log secrets or PII. (NFR-021)
9. **Errors.** RFC 7807 Problem Details with stable error codes (PRD §17). Never empty `catch {}`.
10. **Auth gates.** Email verification required before organizing/handling money (BR-009). Object-level authorization on every read/write (no IDOR).

---

## 6. How to work a slice (the loop)

1. **Pick one vertical slice** from `spec/requirements.yaml` (follow the §26 sequencing: tenancy → identity → leagues → …).
2. **Read the linked FR/NFR** in `PRD.md` and any relevant `spec/test-vectors/`.
3. **Write the failing tests first** from the spec/test-vectors and acceptance criteria.
4. **Implement** the minimum to pass; respect module boundaries and guardrails (§5).
5. **Verify:** `dotnet test` / frontend checks green, OpenAPI lints, migration check passes.
6. **Update `spec/requirements.yaml`** — set `status`, fill `files:` and `tests:` for each FR touched.
7. **Commit** (see §9).

Keep slices atomic (1 concern, ideally 1 module). If it needs more than a few files, split it.

---

## 7. API-first workflow (prevents FE↔BE drift)

- The **contract is `api/openapi.yaml`**. Change it *before* changing controllers or the client.
- Backend DTOs and the frontend TS client are **generated** from it — do not hand-write mismatched types.
- Every UI capability is backed by a documented endpoint (NFR-002). The web app consumes the same API as third parties.
- Versioning: `/api/v1/...`; never break v1 without bumping.
- A Bruno collection is generated from the spec at `web/src/bruno/` (`npm run gen:bruno`). It is committed to git and shared with the frontend team. The CI guard (`gen:bruno:check`) ensures it never drifts from the spec.

---

## 8. Definition of Done (executable — mirrors PRD §22)

A slice is done only when ALL pass:

- [ ] `dotnet build` clean (analyzers/format pass)
- [ ] `dotnet test` green (unit + integration via Testcontainers)
- [ ] Frontend `typecheck` + `lint` + `build` clean (if FE touched)
- [ ] OpenAPI lints and matches implemented endpoints
- [ ] EF migration added + `database update` applies cleanly
- [ ] **Tenant-isolation test** passes (no cross-org leak) for any new tenant-scoped surface
- [ ] Relevant `spec/test-vectors/` covered by tests (bracket/scoring/payout/tie-break work)
- [ ] `spec/requirements.yaml` updated (status + files + tests)
- [ ] No guardrail (§5) violated

**No evidence = not done.**

---

## 9. Commit & PR conventions

- **Conventional Commits + a leading gitmoji.** Examples:
  - `✨ feat(tournament): single-elimination bracket generation (FR-047)`
  - `🐛 fix(finance): remainder-to-captain in team payout split (FR-075a)`
  - `📝 docs: …`  `♻️ refactor: …`  `✅ test: …`  `🔧 chore: …`  `🙈 chore: gitignore …`
- Reference **FR/NFR IDs** in the subject or body so work is traceable.
- Keep commits atomic. Do not commit unless the DoD (§8) for that unit passes.
- **Author = the repo owner only. Never add AI/assistant attribution, `Co-authored-by`, or "generated by" trailers.**
- Do not commit secrets, `.env`, or build artifacts (see `.gitignore`).

---

## 10. Pointers

- Product spec → `PRD.md` (requirements `FR-xxx`/`NFR-xxx`, business rules `BR-xxx`, state machines §10, domain model §9, permissions §11).
- Decisions → `DECISIONS.md`.
- API contract → `api/openapi.yaml`.
- Correctness oracles → `spec/test-vectors/`.
- Coverage tracker → `spec/requirements.yaml`.
