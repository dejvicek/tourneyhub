# TourneyHub — Architecture Decision Records

> Canonical decision log. `PRD.md` links here instead of restating rationale. When a decision changes: add a new ADR that **supersedes** the old one (never edit history), then update the affected requirement(s) in `PRD.md` / `ROADMAP.md`.
>
> Format per ADR: Status · Context · Decision · Consequences · Alternatives considered.

| # | Title | Status |
|---|---|---|
| ADR-001 | Product decisions carried over from PRD v1 (13 resolved questions) | Accepted |
| ADR-002 | Core semantics: recompute cascade, concurrency, outbox, tie-break PRNG | Accepted (ported from .NET ADR-0001, 2026-07-20) |
| ADR-003 | Backend rewritten in Python (FastAPI + SQLAlchemy 2 + PostgreSQL) | Accepted 2026-09-24 — supersedes the backend half of Q-004 |
| ADR-004 | Modular monolith with an explicit module registry | Accepted 2026-09-24 |
| ADR-005 | API contract: code-first OpenAPI with committed spec + drift gate | Accepted 2026-09-24 |
| ADR-006 | Tenancy enforcement: server-resolved org context + tenant session + Postgres RLS | Accepted 2026-09-24 |
| ADR-007 | Realtime via Server-Sent Events + Redis pub/sub (replaces SignalR) | Accepted 2026-09-24 |
| ADR-008 | Authentication: Argon2id, short JWT access token, rotating refresh token | Accepted 2026-09-24 |
| ADR-009 | Database schema conventions | Accepted 2026-09-24 |
| ADR-010 | Background work: in-process worker, no external task queue at MVP | Accepted 2026-09-24 |
| ADR-011 | Frontend stack retained (React + Vite + TS); SPA at MVP, prerender in V1 | Accepted 2026-09-24 |
| ADR-012 | Data-model review gate before any persistence code | Accepted 2026-09-24 |

Residual actions (not decisions): **Q-002a** legal review of the erasure policy before EU hosted launch; **Q-005a** legal review of money handling before hosted paid-entry rollout (V1).

---

## ADR-001 — Product decisions carried over from PRD v1

**Status:** Accepted (unchanged by the rewrite; product scope is stack-independent).

| # | Decision *(ref)* | What we chose | Why |
|---|---|---|---|
| 1 | License *(NFR-019)* | **AGPL-3.0 + CLA** | Copyleft protects the hosted-service commons; CLA preserves dual-licensing. |
| 2 | GDPR erasure vs integrity *(FR-130)* | Sever User↔Participant, hard-delete identity PII, retain **anonymized** match/finance facts | Right-to-erasure reconciled with competition integrity (Recital 26). Tombstoning irreversible. |
| 3 | API style *(§17)* | **REST + JSON only** through V1; `?include=`/`?fields=` + composite endpoints; no GraphQL | Small stable view set; keeps caching/idempotency/ETags simple. |
| 4 | Tech stack *(§21)* | Backend: **superseded by ADR-003**. Frontend: **React + Vite + TS** (kept, ADR-011). DB: **PostgreSQL** (kept). Cache/fan-out: **Redis** (kept). | Frontend and data tier were sound; only the backend language changes. |
| 5 | Money handling *(FR-079–083)* | **Manual ledger at MVP** via a `PaymentProvider` port with a `ManualProvider`; hosted inbound gateway = V1; outbound payouts = Future | Free events run immediately; payments (biggest legal/ops load) stay out of MVP behind a seam. |
| 6 | Teams *(FR-040a/075a/090a)* | `team_size` **1–10**, ad-hoc rosters, a captain (a column with a composite FK into the roster, ADR-009), equal-split payouts, **per-player** points | Covers doubles/esports; per-user standings avoid persistent-team complexity. |
| 7 | Seasons *(BR-002)* | Exactly **one `active` season** per league; divisions = Future | Unambiguous standings. |
| 8 | Disciplines *(FR-040b/040d)* | `Game`→**`Discipline`**; MVP = `winner`+`score`, head-to-head, free-text name | Multi-discipline with an additive path to free-for-all and a catalog. |
| 9 | Result entry *(FR-051)* | `result_entry_mode`: **organizer** (default) + **player_self_report** | Enables distributed play; organizer stays final authority. |
| 10 | Notifications *(FR-140–143)* | **Transactional email only** via a `NotificationChannel` port; hosted = managed provider, self-host = SMTP | Email underpins verification/invites; seam keeps channels additive. |
| 11 | Admin bootstrap *(FR-009a–d)* | Hosted: platform operator + per-org Owner. Self-host: env-configured bootstrap admin; first-user-admin opt-in; one-shot, audited, ≥1 admin | Stops a random visitor claiming admin on first boot. |
| 12 | Spectator *(FR-028a/b)* | **Capability level, not a role**; MVP adds follow/favourite | Falls out of the league-scoped role model. |
| 13 | Best-of-N *(FR-040c)* | **Aggregate result only** (winner + e.g. `2–1`); per-set capture = Future | Captures set/map sports without a `match_games` sub-model. |

---

## ADR-002 — Core semantics: recompute cascade, concurrency, outbox, tie-break PRNG

**Status:** Accepted. Ported from the .NET-era ADR-0001 (2026-07-20); C#/SignalR specifics replaced, semantics unchanged.
**References:** BR-104, FR-095, FR-058, FR-062, FR-057, FR-141, FR-060–064, FR-059, NFR-018, NFR-023, E-06/08/10/21. Constrains `spec/test-vectors/*.json`.

### 2.1 Result-edit recompute cascade

- **Standings, advancement and payout amounts are persisted derived state**, produced by a **pure, deterministic recompute function**: `recompute(matches, format_config, scoring_config, rng_seed) → (standings, advancement, payout_calc)`. No DB access, no wall clock, no randomness beyond `rng_seed`. Match results are the only source of truth.
- **Write path:** (1) validate + persist the result under the `matches.version` check → (2) in the **same transaction** run `recompute` and upsert `tournament_standings`, `season_standings`, `match_slots` advancement, `payouts (calculated)` → (3) append `audit_events` in the same transaction → (4) insert `outbox_events` in the same transaction; delivery happens after commit. Because season standings must land inside this transaction, the `tournaments` module owns that table (`DATA-MODEL.md` §2).
- **Invariant:** after any commit, `persisted_derived == recompute(source)` (an admin integrity check verifies it; manual tie-break overrides are the only expected difference).
- **Sync vs async:** competition state (standings, advancement, payout *calculation*) is synchronous in the write transaction. Payout *approval/payment*, notifications and realtime fan-out are asynchronous via the outbox.
- **Editing a result in a `completed` tournament** is allowed for organizer/owner, always audited, and **implicitly reopens** the tournament (`completed → in_progress`, FR-059/E-21). When every final match is resolved again it transitions back to `completed`.
- **Approved/paid payouts are never silently mutated.** If a recompute changes an amount for a payout in `approved`/`paid`, the old row is marked `voided` (with `replaced_by_payout_id`), a new `calculated` row is written, and the response carries `warnings: ["payouts_require_reapproval"]`.

### 2.2 Concurrency conflict semantics

| Operation | Mechanism |
|---|---|
| Match result edit, registration state change, payment status, payout approval | `If-Match: "<version>"` on the aggregate → **409** `concurrency_conflict` with the current ETag; client refetches and retries. Missing `If-Match` on a versioned mutation → **428** `precondition_required`. |
| Season activation, bracket generate/regenerate, org ownership transfer, tournament state changes | **Domain guard first** (unique partial index / state machine / ≥1 owner) → **422** with a domain code (`season_already_active`, `bracket_already_generated`, `org_owner_required`, `invalid_tournament_state`), **then** `If-Match` on the parent aggregate. |

`version` is an explicit `int` column, managed by SQLAlchemy's `__mapper_args__ = {"version_id_col": ...}` rather than hand-written increments (the ORM emits `UPDATE … WHERE id = ? AND version = ?` and raises `StaleDataError` when it matches 0 rows). It is returned as the `ETag` header on single-resource GETs and inside list items. Every write that emits an outbox event **must** bump it — see §2.3.

### 2.3 Outbox and realtime delivery

- **At-least-once** delivery. The relay (ADR-010) polls `outbox_events WHERE published_at IS NULL` with `FOR UPDATE SKIP LOCKED`, publishes to Redis channel `org:{org_id}:tournament:{id}:{public|organizer}` and to notification handlers, then stamps `published_at`. Failures back off exponentially (`next_attempt_at`), max 10 attempts, then alert.
- **Ordering key:** `(aggregate_type, aggregate_id, aggregate_version)`; strictly ordered per aggregate, unordered across aggregates.
- **Consumer dedup:** SSE clients track the last `aggregate_version` per subscription and drop replays; `notification_deliveries` is unique per `(outbox_event_id, channel, recipient)`.
- **Producer invariant:** every outbox emission **must** bump the aggregate's `version`. Two events of the same type at the same version collide on `UNIQUE(aggregate_type, aggregate_id, aggregate_version, event_type)` and abort the write transaction.
- **Snapshot-then-resume:** client `GET /tournaments/{id}/overview` (returns `version` as ETag) → opens the SSE stream with `Last-Event-ID: <version>` → server replays events with `aggregate_version > Last-Event-ID` from a Redis stream buffer (last 500 events per channel, 24 h) → on a gap (`aggregate_version > last + 1` and not replayable) the client refetches the snapshot. **Polling fallback:** `GET …/overview` with `If-None-Match` every 5 s, backing off to 30 s (FR-063).

### 2.4 Tie-break PRNG determinism

- Last-resort `random` tie-breaker uses **splitmix64** seeded from `SHA-256(rng_seed_bytes || tie_break_index.to_bytes(4,'big'))[:8]` (big-endian unsigned), applied as a Fisher–Yates shuffle over the tied participant ids **sorted lexicographically by canonical UUID string**.
- `rng_seed` is a UUID generated server-side at tournament creation and immutable thereafter — the only entry point for randomness (also used for `seeding_method='random'`).
- The deterministic order is authoritative by default. An organizer **manual override** is stored on `tournament_standings.tie_broken_manually` plus an audit row, takes precedence for display/payout/advancement, and is discarded (audited) if a result edit changes the tie group.
- Reference implementation (pure 64-bit arithmetic; identical in Python and TypeScript):

```text
splitmix64(state):
    state = (state + 0x9E3779B97F4A7C15) mod 2^64
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) mod 2^64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) mod 2^64
    return z ^ (z >> 31)
```

Golden vectors for the shuffle are added to `spec/test-vectors/tie-breaks.json` with the first tie-break slice and must be satisfied by both the Python and the TypeScript implementation.

### 2.5 Tests this ADR mandates

Recompute determinism (property test: same inputs → identical output), recompute idempotency (re-running on persisted state is a no-op), cascade integration (edit in completed tournament → reopen, standings recalculated, approved payouts voided, audit written), 409 on concurrent match edits, 422 on concurrent season activation, outbox at-least-once + dedup, SSE snapshot-then-resume + gap detection, splitmix64 cross-language vectors, manual tie-break override precedence.

---

## ADR-003 — Backend rewritten in Python

**Status:** Accepted 2026-09-24. Supersedes the backend half of PRD-v1 Q-004 (.NET 8 / ASP.NET Core / EF Core / SignalR).

**Context.** The owner wants to rebuild from scratch with a Python backend, keep the React frontend, review the data model before code, and grow from MVP to a full product by adding modules. Requirements that shaped the choice: API-first with generated OpenAPI (NFR-002/015), strict typing for a finance/audit domain, async realtime fan-out (FR-060), PostgreSQL with JSONB and partial indexes, property-based tests (NFR-013), and small-team velocity.

**Decision.**

| Layer | Choice | Notes |
|---|---|---|
| Runtime | **Python 3.13**, **uv** for env/lock/scripts | `uv run`, `uv lock` committed. |
| Web framework | **FastAPI** (Starlette, ASGI) on **uvicorn** | Native OpenAPI 3.1 generation from Pydantic models, async, dependency injection for tenant/auth context. |
| Validation / DTOs | **Pydantic v2** (`model_config = ConfigDict(extra="forbid", strict=True)`) | Request/response schemas *are* the API contract (ADR-005). |
| ORM / DB access | **SQLAlchemy 2.0** (typed `Mapped[]`, async engine via **asyncpg**) | Repositories per module; raw SQL allowed for heavy stats/reads. |
| Migrations | **Alembic**, single history, hand-reviewed (autogenerate as a draft only) | `alembic check` in CI. |
| Settings | **pydantic-settings**, env only, prefix `TOURNEYHUB_` | Startup fails fast on missing/invalid config; email settings validated (FR-142). |
| Auth primitives | **argon2-cffi** (Argon2id), **PyJWT** (HS256 at MVP, key ≥ 32 bytes; RS256 optional later) | ADR-008. |
| Redis | **redis-py** (asyncio) | Pub/sub + stream buffer for SSE, rate-limit counters, small caches. |
| Email | **aiosmtplib** (self-host SMTP, Mailpit in dev) + provider adapter via **httpx** (Resend/Postmark/SES — one chosen at hosted launch) | Behind `NotificationChannel` port. |
| Logging / observability | **structlog** JSON logs with correlation id; `/health/live`, `/health/ready`; **OpenTelemetry** hooks optional | NFR-014. PII/secrets scrubbed by a processor. |
| Tests | **pytest** + **pytest-asyncio**, **hypothesis** (property-based), **testcontainers-python** (real Postgres + Redis), **schemathesis** (contract fuzz, optional), **Playwright** (web e2e) | NFR-013. |
| Quality gates | **ruff** (lint+format), **mypy --strict**, **import-linter** (module boundaries, ADR-004), **bandit** (security lint), **pip-audit** | All in CI, all block merge. |
| Packaging / deploy | Single Docker image; `tourneyhub api` and `tourneyhub worker` entry points; docker-compose for self-host | Same image for hosted and self-host (A-002). |

**Consequences.**
- Money math uses Python `int` (arbitrary precision) on minor units; `decimal.Decimal` only for percentage → minor-unit conversion with `ROUND_HALF_EVEN`; `float` is banned in `finance` and `competition` packages (ruff custom rule + test).
- Determinism paths (`bracket`, `seeding`, `ranking`) must not import `random`, `time`, `datetime.now`, or `uuid.uuid4` — enforced by import-linter contracts and a unit test that scans the AST.
- OpenAPI is generated from code, so the contract-first discipline is enforced by a committed spec + CI drift check rather than by hand-authoring YAML first (ADR-005).
- Team must know async SQLAlchemy pitfalls (no lazy loads across awaits; explicit `selectinload`).

**Alternatives considered.**
- **Django + DRF/Ninja:** batteries (admin, auth) but sync-first ORM, weaker typing, admin unsuitable for a tenant-isolated product; multi-tenancy libraries impose schema-per-tenant. Rejected.
- **Litestar:** excellent typing and DI, smaller ecosystem/hiring pool than FastAPI. Rejected for ecosystem reasons; the architecture would port trivially.
- **Keep .NET:** rejected by the owner's brief.

---

## ADR-004 — Modular monolith with an explicit module registry

**Status:** Accepted 2026-09-24. Implements NFR-001/003, FR-042, and the owner's requirement that new modules be easy to add (see `ROADMAP.md`).

**Decision.** One deployable, one database, one Alembic history, but code is organised as **self-contained modules** under `src/tourneyhub/modules/<name>/` with a fixed internal layout and an explicit dependency DAG.

```
src/tourneyhub/
  core/                 # cross-cutting kernel: settings, db session, tenant context, auth deps,
                        # errors (RFC 7807), outbox/audit ports, module registry, ids, time, money
  modules/
    <name>/
      __init__.py       # exports `module = ModuleManifest(...)`
      domain/           # pure: entities, value objects, state machines, pure functions (no IO, no ORM)
      application/      # use cases / services, ports (Protocols), DTO mapping; depends on domain + core
      infrastructure/   # SQLAlchemy models + repositories, adapters (email, redis, providers)
      api/              # FastAPI routers, request/response schemas, dependencies
      events.py         # domain event types this module publishes + handlers it subscribes to
      permissions.py    # capability keys this module defines and their default role grants
      tests/            # module-local unit tests (integration tests live in /tests)
```

```python
@dataclass(frozen=True)
class ModuleManifest:
    name: str                              # "tournaments"
    depends_on: tuple[str, ...]            # ("leagues", "identity", "platform")
    routers: tuple[APIRouter, ...]         # mounted under /api/v1
    models: tuple[type[Base], ...]         # for metadata / alembic discovery
    event_handlers: tuple[EventHandler, ...]
    permissions: tuple[Permission, ...]
    format_plugins: tuple[TournamentFormat, ...] = ()   # registry contributions (FR-042)
    payment_providers: tuple[PaymentProvider, ...] = ()
    notification_channels: tuple[NotificationChannel, ...] = ()
    scheduled_jobs: tuple[ScheduledJob, ...] = ()
```

- `core/registry.py` loads the manifests listed in `TOURNEYHUB_MODULES` (default: all built-in), **topologically sorts by `depends_on`**, rejects cycles, mounts routers, registers models, handlers, permissions and plugins.
- **Boundary rules (import-linter):** `domain` imports nothing from `application/infrastructure/api`; a module may import another module **only** through `modules/<other>/application/public.py` (its published service interface + DTOs) — never its ORM models, repositories or routers; `core` imports no module.
- **Cross-module writes** happen via **domain events** (in-process, synchronous within the transaction for consistency-critical reactions; via the outbox for eventual reactions) or via the other module's public service — never via a shared table.
- **Extension registries** (`FormatRegistry`, `PaymentProviderRegistry`, `NotificationChannelRegistry`, `ScoringPresetRegistry`) are dictionaries populated from manifests; adding a format or provider is a new module (or a new plugin in an existing one) with **no core changes** (Open/Closed).
- The **module-add recipe** lives in `CLAUDE.md` §7; `ROADMAP.md` lists planned modules and the seams the MVP reserves for them.

**MVP modules and DAG:** `platform` ← `identity` ← `invitations`; `platform, identity` ← `leagues` ← `tournaments` ← `finance`; `platform` ← `realtime`. `reporting` (V1) depends on all competition/finance modules read-only.

**Composite operations at the composition root.** Some operations legitimately span two modules in the direction the DAG forbids. Closing a season is the canonical case: the state lives in `seasons` (owned by `leagues`) while the standings it must freeze live in `season_standings` (owned by `tournaments`, see `DATA-MODEL.md` §2), and BR-003 requires the snapshot to exist the instant the season is `closed`, so an event cannot be used. Neither module may call the other.

The resolution is that the **route handler** — which sits above every module and may import any of them — orchestrates the two calls inside one transaction, passing data as parameters rather than letting one module read the other's tables:

```python
# api layer, not inside a module
standings = await tournaments.public.get_season_standings(session, season_id)
await leagues.public.close_season(session, season_id, standings=standings)
```

The same pattern serves the composite reads the modules cannot assemble alone: the tournament `overview` endpoint and the registration list with payment state (`DATA-MODEL.md` §8.4). Modules stay leaves; composition is the application's job, and import-linter keeps it that way.

**Alternatives considered.** Microservices (operational overhead unjustified at ≤10k users), Django apps (ADR-003), flat layered architecture without module boundaries (the .NET attempt showed boundaries erode without tooling — hence import-linter as a gate).

---

## ADR-005 — API contract: code-first OpenAPI with committed spec + drift gate

**Status:** Accepted 2026-09-24. Refines PRD §17 and NFR-002/015.

**Decision.**
- The contract is **generated from FastAPI/Pydantic** and committed at `api/openapi.json`. CI runs `uv run tourneyhub openapi export` and fails on any diff (**drift gate**). A PR that changes the API must include the regenerated spec, which makes API changes reviewable as a diff.
- The frontend types are generated from that file with `openapi-typescript` (`npm run gen:api`); the Bruno collection is generated with `@usebruno/cli` (`npm run gen:bruno`, drift-checked by `gen:bruno:check`). Hand-written mirrors of DTOs are forbidden.
- Conventions: base path `/api/v1`; RFC 7807 `application/problem+json` with stable `code` (see `spec/error-catalog.md`); cursor pagination (`?cursor=&limit=`) for append-heavy lists, `?page=&limit=` for small lists; allow-listed `?sort=`, `?include=`, `?fields=`; `Idempotency-Key` on POSTs that create registrations/payments/payouts and on `POST /auth/register`; `ETag`/`If-Match` on versioned resources; `X-Correlation-Id` echoed on every response; per-IP and per-user rate limits (stricter on `/auth/*`).
- Public read endpoints live under `/api/v1/public/...` and are the only routes that accept anonymous callers.

**Alternatives considered.** Hand-authored `openapi.yaml` first with server stubs generated (the previous approach): with FastAPI this doubles the work and drifts anyway; the committed-spec gate gives the same review benefit.

---

## ADR-006 — Tenancy enforcement

**Status:** Accepted 2026-09-24. Implements NFR-004/024, FR-151/152/154, BR-012/015.

**Decision.** Three layers, each independently sufficient to stop a cross-org read:

1. **Server-resolved org context.** A FastAPI dependency `current_org()` resolves the organization from (a) the URL (`/orgs/{org_slug}/…` or public slugs) **and** (b) the caller's `organization_memberships` (or platform-admin flag). Request bodies and query strings can never select the tenant. Failure → 404 `not_found` (do not confirm existence) or 400 `no_tenant_resolved` for routes that require an org but got none.
2. **Tenant-scoped session.** Every repository receives a `TenantSession` that wraps the SQLAlchemy session, holds `org_id`, adds `WHERE organization_id = :org` to every query on `TenantScoped` models via `with_loader_criteria`, stamps `organization_id` on insert, and raises if an entity from a different org is attached. Platform-admin listing endpoints and retention jobs use an explicit `AdminSession` that logs its use.
3. **Postgres Row-Level Security** on every tenant table (policy in `DATA-MODEL.md` §11.2). The session issues `SET LOCAL app.current_org_id` at transaction start, and the policy reads it through `NULLIF(..., '')::uuid` so an empty GUC denies rather than raising.

   This layer only exists if the connection role is right: **RLS never applies to a superuser**, and `FORCE ROW LEVEL SECURITY` only covers the table *owner*. Hence three roles (`DATA-MODEL.md` §11.1) — `tourneyhub_migrator` owns the schema, `tourneyhub_app` is `NOINHERIT` with neither superuser nor `BYPASSRLS` and is what the API connects as, and `tourneyhub_admin` (`BYPASSRLS`) serves `AdminSession`, the outbox relay, retention and platform-admin listings. A startup assertion and a test check `pg_roles` for the app role.

   Views are a second trap: without `WITH (security_invoker = true)` a view runs with its owner's privileges, so RLS may not apply at all. Both views in `DATA-MODEL.md` §10 set it.

4. **Composite tenant foreign keys** (`DATA-MODEL.md` §1.1): every tenant-scoped FK carries `organization_id` against a parent `UNIQUE (id, organization_id)`. A cross-org row cannot be written at all, rather than being written and then hidden from both tenants by RLS.

Also: SSE channels and Redis keys are prefixed with `org:{org_id}`; exports run inside a tenant session; caches key on `org_id`; audit rows carry `organization_id`.

**Consequences.** Every new tenant table needs the mixin, the RLS policy, the composite FK and the grants in its migration. `alembic check` sees none of those, so a schema-objects test reads `pg_policies`, `pg_trigger` and `information_schema.table_privileges` after `upgrade head` and compares them with an expected inventory (`DATA-MODEL.md` §12). An **isolation test** (two orgs, same fixtures, every endpoint) is part of the Definition of Done for any tenant-scoped surface.

**Alternatives considered.** Schema-per-tenant (migration fan-out, breaks self-host simplicity), database-per-tenant (hosted cost), app-filter only (a single forgotten `WHERE` is a P0 leak; RLS closes that class of bug).

---

## ADR-007 — Realtime via Server-Sent Events + Redis pub/sub

**Status:** Accepted 2026-09-24. Replaces SignalR (PRD-v1 §16) for FR-060–064, NFR-006/007.

**Context.** Realtime traffic is one-directional: server → spectator/organizer clients. All writes go through REST (FR-062). SignalR is .NET-specific.

**Decision.**
- **SSE** (`text/event-stream`) endpoint `GET /api/v1/orgs/{org}/tournaments/{id}/events?channel=public|organizer` (via `sse-starlette`). Public channel requires no auth for `public`/`unlisted` tournaments; `organizer` channel requires an organizer/owner role (FR-064). Events carry `id: <aggregate_version>`, `event: <event_type>`, `data: <json>`; the browser's native `EventSource` auto-reconnects and sends `Last-Event-ID`, which maps directly onto ADR-002 §2.3 snapshot-then-resume.
- **Fan-out** across API instances via Redis pub/sub on `org:{org}:tournament:{id}:{channel}`; a per-channel **Redis stream** (`XADD … MAXLEN 500`) buffers recent events for replay on reconnect.
- **Fallback:** ETag polling of the composite `overview` endpoint (FR-063).
- Heartbeat comment every 15 s; connection cap per IP; `organizer` payloads never sent on `public`.

**Alternatives considered.** WebSockets (bidirectional not needed; harder through proxies/HTTP/2; needs a client library), long-polling only (latency, load), third-party push service (vendor lock-in for a self-hostable product). WebSockets can be added later as another `realtime` transport without touching producers.

---

## ADR-008 — Authentication

**Status:** Accepted 2026-09-24. Implements FR-001–005, FR-010, NFR-009, BR-009.

**Decision.**
- Passwords hashed with **Argon2id** (argon2-cffi defaults: t=3, m=64 MiB, p=4), rehash-on-login when parameters change. Minimum 12 characters, no composition rules, breached-password check via HIBP k-anonymity range API (fail-open with a warning if the API is down).
- **Access token:** JWT (HS256, 15 min) carrying `sub`, `sid` (session/family id), `pa` (platform admin flag). Sent as `Authorization: Bearer` by the SPA (kept in memory, not localStorage) and by third-party clients.
- **Refresh token:** opaque 256-bit random, stored **hashed**, **rotating** with family-reuse detection (`refresh_tokens`), 30-day sliding expiry. Delivered to the SPA as an `HttpOnly; Secure; SameSite=Strict` cookie scoped to `/api/v1/auth/refresh` (CSRF-safe because the cookie is only read by that one endpoint and the SPA sends a custom header). Third-party clients receive it in the JSON body instead.
- Email verification and password reset use single-use hashed tokens (`auth_tokens`). Unverified users can log in but hit 403 `email_not_verified` on organizing/money endpoints (BR-009).
- Lockout: exponential backoff after 5 failed logins per account and per IP. Counters live in **Redis**, not on `users` — a failed-login `UPDATE` there would bump the row's `version` and break the ETag of a concurrent profile `PUT`. Sessions revoked on password change, ban, or suspension.
- OAuth (Google/GitHub) and TOTP are V1 (`ROADMAP.md` M-AUTH+).

**Alternatives considered.** Server sessions only (fine for the SPA, awkward for third-party API consumers), long-lived JWTs without refresh (no revocation), external IdP (self-host burden).

---

## ADR-009 — Database schema conventions

**Status:** Accepted 2026-09-24. Full rules in `DATA-MODEL.md` §1; summary of the non-obvious choices:

- **UUIDv7 primary keys generated in the application** via `uuid-utils` (time-ordered; no central sequence; safe to create ids before insert for outbox payloads). `uuid.uuid7()` is stdlib only from Python 3.14, and a DB-side `DEFAULT gen_random_uuid()` is banned because it breaks the time ordering cursor pagination relies on.
- **`text` + `CHECK` for enumerations** instead of Postgres enums (cheap to widen, no `ALTER TYPE` locks).
- **`bigint` minor units + `text` currency with `CHECK (currency ~ '^[A-Z]{3}$')`** for all money; no `numeric`, and no `char(n)` (blank-padded, surprising when compared against a `text` parameter). Money and basis points are never stored inside `jsonb`, which enforces no type and decodes decimals to `float`.
- **Integer thousandths (`points_milli`)** for scoring points to keep ranking arithmetic exact and cross-language.
- **Explicit `version int`** for optimistic concurrency (not `xmin`), so the ETag is stable, portable and visible in payloads.
- **Persisted derived tables** for standings/payouts with `source_version` provenance.
- **Two audit tables** (`audit_events` tenant-scoped NOT NULL, `platform_audit_events` global) so the tenant guardrail never needs a nullable exception.
- **Membership tables carry roles; no `owner_id` columns** on leagues/orgs (one source of truth, uniqueness by partial index). A team **captain** is the documented exception: `participants.captain_user_id` with a composite FK into `participant_members (participant_id, user_id)`, because the FK guarantees the captain is actually on the roster — which a role row cannot.
- **Composite tenant foreign keys**: tenant-scoped FKs carry `organization_id` against a parent `UNIQUE (id, organization_id)`, so a cross-org row is structurally impossible rather than merely hidden by RLS (`DATA-MODEL.md` §1.1).
- **Competition ranks may be shared**; a separate unique `order_index` carries the deterministic display order, so the tie-break PRNG never decides money (`DATA-MODEL.md` §8.7).
- **Three database roles** (`tourneyhub_migrator` / `_app` / `_admin`): RLS never applies to a superuser and `FORCE RLS` only covers the table owner, so the app must connect as a role that is neither (`DATA-MODEL.md` §11.1).

---

## ADR-010 — Background work

**Status:** Accepted 2026-09-24.

**Decision.** A single `tourneyhub worker` process (same image, same code) runs an asyncio supervisor with: the **outbox relay** (ADR-002 §2.3), **notification sender**, **self-report timeout sweeper** (FR-051a), **registration deadline / unpaid policy** (V1), **retention purge** (audit IP/UA, deleted-account anonymization after grace, published outbox rows), **audit partition lifecycle** (create next month's partition ahead of time, drop partitions past the audit horizon — `DATA-MODEL.md` §4.3), **inactivity flagging** (V1). Jobs are idempotent and leader-elected via a Redis lock so multiple workers are safe.

Most jobs are tenant-iterating (each org in its own tenant session). Three are not, and each names its connection explicitly: the outbox relay and the retention purge run as `tourneyhub_admin` (`BYPASSRLS`), and the partition lifecycle is DDL on owned tables, so it runs as the **migrator** role — the only job that does. No Celery/RQ/Dramatiq at MVP; the `ScheduledJob` manifest entry (ADR-004) is the seam if a real queue is ever needed.

**Alternatives considered.** Celery (broker + result backend + another runtime to operate for a handful of jobs), arq (fine, but the outbox already needs a custom loop; adding it later is cheap).

---

## ADR-011 — Frontend stack retained

**Status:** Accepted 2026-09-24. Keeps PRD-v1 Q-004 frontend half and the existing `web/` conventions.

**Decision.** **React 19 + Vite + TypeScript (strict)**, **Tailwind CSS v4** with the design tokens in `design/tokens.css` as CSS variables, **TanStack Query** for server state (ETag-aware fetch wrapper; `If-Match` on mutations; 409 → refetch + toast), **react-router v7**, **react-i18next** (no hard-coded user strings, NFR-012), **openapi-typescript** generated client types from `api/openapi.json`, **Bruno** collection generated from the same spec, **ESLint + oxlint**, **Playwright** e2e. Native `EventSource` for SSE (ADR-007). Mobile-first (NFR-011), light theme at MVP, dark mode via tokens in V1.

**Public-page SEO:** MVP ships the SPA with server-injected OpenGraph/meta tags for public routes; full prerender/SSG of public pages is a **V1** hardening item (`ROADMAP.md`). Rationale: it is an optimisation with no data-model or API impact and should not delay the MVP core.

---

## ADR-012 — Data-model review gate

**Status:** Accepted 2026-09-24. Owner requirement.

**Decision.** `DATA-MODEL.md` carries a status line. While it reads `DRAFT`, agents may scaffold the project, tooling, CI, pure domain code (formats, scoring, money math against `spec/test-vectors/`) and the frontend shell, but **must not** write SQLAlchemy models, Alembic migrations, repositories, or API endpoints that persist data. When the owner sets `APPROVED <date>`, persistence work begins and any later schema change requires (1) a `DATA-MODEL.md` edit in the same PR and (2) a note in the PR description. The gate and the reserved seams exist so that later modules (`ROADMAP.md`) can be added by **additive** migrations only.
