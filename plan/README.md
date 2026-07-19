# TourneyHub — Implementation Plan

> **Purpose.** This is the executable build plan for TourneyHub. Each step below is a
> self-contained markdown file under `plan/`. An AI (or engineer) can pick up **one step
> file + `PRD.md`** and complete it without further context. Work steps top-to-bottom,
> respecting the `Depends on` column.
>
> **Governing docs:** [`PRD.md`](../PRD.md) (requirements, governs) · [`DECISIONS.md`](../DECISIONS.md) ·
> [`AGENTS.md`](../AGENTS.md) (guardrails + DoD) · [`api/openapi.yaml`](../api/openapi.yaml) (contract) ·
> [`spec/requirements.yaml`](../spec/requirements.yaml) (coverage) · [`spec/test-vectors/`](../spec/test-vectors/) (oracles).

---

## 1. Current state (senior review, condensed)

The repo today is a **disciplined foundation, ~2% functionally complete** (`requirements.yaml`: 0 done, 4 in-progress, ~138 not-started). Strong: contract-first OpenAPI, golden test-vectors, guardrail tests (tenant isolation, module boundaries, money type), clean-arch skeleton, CI, conventional commits.

**Reality gaps this plan fixes first (Phase 0):**
- **Tenancy is a DbContext demo, not a boundary** — `ITenantContext`/`AddDbContext` are only a comment in `Program.cs`; no request→auth→org resolution; no FK on `organization_id`; guard stamps `Guid.Empty` instead of failing closed.
- **Optimistic concurrency is hollow** — `Entity.Version` exists but is not an EF concurrency token; no ETag/`If-Match`/409.
- **CI is theatre in places** — spins Postgres/Redis that no test uses; integration tests are SQLite-only; migration never applied; no dependency/secret scanning; `/health/ready` returns 200 unconditionally.
- **Missing meta** — no `LICENSE` (AGPL-3.0 is Decision #1), no `.editorconfig`/analyzers/`Directory.Packages.props`, no `CONTRIBUTING`.
- **Under-specified hard problems** — result-edit recompute cascade, concurrency conflict semantics, realtime outbox delivery guarantees, tie-break PRNG. Settled once in `03-adr-core-semantics.md`.
- **One model mismatch** — league standings are per-User (`FR-090a`) but the contract's `Standing` is participant-based. Split in `16-rankings-standings-public.md`.

## 2. Recommended MVP cut (senior judgment)

The PRD's §4.1 MVP is too broad to ship as one release. This plan **covers the full PRD scope** (nothing dropped), but tags each step and **recommends** the following move to **V1** for the first shippable release. Steps are tagged `MVP` / `MVP*` (PRD-MVP but recommend-defer) / `V1` / `Future`.

- Defer **team play** (`12` team parts, `19`), **player self-report** (part of `15`), **live push** (`17` → poll first), **finance** (`18`–`19`), **discovery/follow** (part of `10`). Ship **individual, organizer-run, single-elimination tournaments** first.

Each step's header states its scope tag so you can build the recut MVP by doing only `MVP`-tagged steps (+ their deps).

## 3. How to work a step

1. Open the step file + `PRD.md`. Read the linked FR/NFR/BR and any `spec/test-vectors/`.
2. **Contract-first**: if the step adds/changes API, edit `api/openapi.yaml` first (regenerate FE types).
3. **Write the failing tests first** (from the step's Tests section + test-vectors).
4. Implement the minimum; respect the guardrails (AGENTS.md §5).
5. Verify: `dotnet build`/`dotnet test` green, OpenAPI lints, migration applies, FE checks pass.
6. Update `spec/requirements.yaml` (status + files + tests) for every FR touched.
7. Commit (Conventional Commits + gitmoji, per AGENTS.md §9). One concern per commit.

**Definition of Done** for every step = AGENTS.md §8 + the step's own DoD. **No evidence = not done.**

## 4. Step index

Legend — Scope: `MVP` (ship first) · `MVP*` (PRD-MVP, recommend defer to V1) · `V1` · `Future`. Status: ⬜ not started · 🟨 partial · ✅ done.

### Phase 0 — Foundation & correctness (do first; unblocks everything)
| # | File | Title | Scope | Depends on | Goal |
|---|---|---|---|---|---|
| 00 | [`00-project-meta-and-tooling.md`](./00-project-meta-and-tooling.md) | Project meta & tooling hardening | MVP | — | LICENSE, editorconfig+analyzers, central pkgs, CI scanning + real-Postgres tests + migration apply, real health checks |
| 01 | [`01-tenancy-end-to-end.md`](./01-tenancy-end-to-end.md) | Tenancy as a real boundary | MVP | 00 | Wire `ITenantContext`+DbContext in API, fail-closed, FK + immutable `organization_id`, WebApplicationFactory multi-org test |
| 02 | [`02-api-conventions-and-concurrency.md`](./02-api-conventions-and-concurrency.md) | API conventions & optimistic concurrency | MVP | 01 | RFC7807 + error catalog, pagination, idempotency, rate limiting, correlation IDs; real `Version` concurrency token + ETag/`If-Match`/409 |
| 03 | [`03-adr-core-semantics.md`](./03-adr-core-semantics.md) | ADR: recompute/concurrency/outbox/PRNG | MVP | — | Design note (no code) settling result-edit recompute, conflict semantics, outbox delivery, tie-break PRNG |
| 04 | [`04-audit-outbox-notifications-seam.md`](./04-audit-outbox-notifications-seam.md) | Audit log + outbox + notification seam | MVP | 01, 03 | Append-only `AuditEvent`, transactional outbox, `INotificationChannel`/`EmailChannel` port |

### Phase 1 — Identity & organizations
| # | File | Title | Scope | Depends on | Goal |
|---|---|---|---|---|---|
| 05 | [`05-auth-accounts.md`](./05-auth-accounts.md) | Auth & accounts | MVP | 00,01,02 | register/verify/login/reset, password policy, account states, verification gate (BR-009) |
| 06 | [`06-organizations-and-membership.md`](./06-organizations-and-membership.md) | Organizations & membership | MVP | 01,05 | Org self-signup → OrgOwner, ownership transfer (≥1 owner), multi-org active-org resolution, permissions layer |
| 07 | [`07-platform-admin-and-bootstrap.md`](./07-platform-admin-and-bootstrap.md) | Platform admin & self-host bootstrap | MVP | 06 | Env bootstrap admin, first-user opt-in, ≥1 InstanceAdmin, org suspend/reactivate |
| 08 | [`08-invitations.md`](./08-invitations.md) | Invitations | MVP | 06,04 | Email/link invites, state machine, TTL, resolve-on-signup |
| 09 | [`09-notifications-transactional.md`](./09-notifications-transactional.md) | Transactional notifications | MVP | 04,05,08 | Verification/reset/invite/roster/self-report emails via outbox → EmailChannel; hosted provider + self-host SMTP |

### Phase 2 — Competition core
| # | File | Title | Scope | Depends on | Goal |
|---|---|---|---|---|---|
| 10 | [`10-leagues-and-seasons.md`](./10-leagues-and-seasons.md) | Leagues & seasons | MVP | 06 | League CRUD + visibility, one active season, immutable snapshots, public pages; follow/discovery = MVP* |
| 11 | [`11-scoring-system-config.md`](./11-scoring-system-config.md) | Scoring system config | MVP | 10 | Data-driven `score(result,config)`, presets, ordered tie-breakers |
| 12 | [`12-tournaments-participants-rosters.md`](./12-tournaments-participants-rosters.md) | Tournaments, participants & rosters | MVP | 10 | Tournament create, `resultModel`, registration window; teamSize/roster = MVP* |
| 13 | [`13-single-elimination-bracket.md`](./13-single-elimination-bracket.md) | Single-elimination bracket | MVP | 12 | Deterministic gen from seeds + `rng_seed`, byes to top seeds; `single-elimination.json` |
| 14 | [`14-round-robin-and-tiebreaks.md`](./14-round-robin-and-tiebreaks.md) | Round-robin & tie-breaks | MVP* | 11,12 | Pairings + standings + ordered tie-breakers; `round-robin.json`, `tie-breaks.json` |
| 15 | [`15-match-results-and-recompute.md`](./15-match-results-and-recompute.md) | Match results, validation & recompute | MVP | 02,03,13 | Result entry/validation, forfeits/withdrawals, override, recompute cascade (per ADR); self-report = MVP* |
| 16 | [`16-rankings-standings-public.md`](./16-rankings-standings-public.md) | Rankings, standings & public reads | MVP | 11,15 | Split participant-standings vs user-standings, snapshots, composite overview |
| 17 | [`17-live-realtime-gateway.md`](./17-live-realtime-gateway.md) | Live/realtime gateway | MVP* | 04,16 | SignalR + Redis backplane, org-scoped channels, snapshot-on-reconnect; poll-first fallback |

### Phase 3 — Finance
| # | File | Title | Scope | Depends on | Goal |
|---|---|---|---|---|---|
| 18 | [`18-fees-payments-prizepool.md`](./18-fees-payments-prizepool.md) | Fees, payments & prize pool | MVP* | 12,16 | Entry fee, payment status FSM, prize pool math, `IPaymentProvider`/`ManualProvider`; `payout-split.json` |
| 19 | [`19-payouts-and-team-splits.md`](./19-payouts-and-team-splits.md) | Payouts & team splits | MVP* | 18 | Payout per standing, team split (remainder→captain), payout FSM |

### Phase 4 — Hardening / V1
| # | File | Title | Scope | Depends on | Goal |
|---|---|---|---|---|---|
| 20 | [`20-gdpr-privacy.md`](./20-gdpr-privacy.md) | GDPR & privacy | MVP | 05,16 | Export, tombstone deletion, consent, retention; integrity preserved |
| 21 | [`21-reporting-and-exports.md`](./21-reporting-and-exports.md) | Reporting & exports | V1 | 16,19 | Report views, CSV, refunds, configurable prize distribution |
| 22 | [`22-hosted-inbound-payments.md`](./22-hosted-inbound-payments.md) | Hosted inbound payments | V1 | 18 | One gateway, webhook-authoritative status; gated on legal review (Q-005a) |

## 5. Step-file template

Every step file MUST follow this structure so it is self-contained:

```markdown
# Step NN — <Title>

- **Scope:** MVP | MVP* | V1 | Future
- **Status:** ⬜ not started
- **Depends on:** <step ids or —>
- **Unblocks:** <step ids>
- **Requirements:** FR-xxx, NFR-xxx, BR-xxx (link to PRD sections)

## Goal
1–3 sentences: what "done" delivers.

## Context & why
Why this step exists; ties to PRD + review findings; key risks.

## Design notes (decisions & gotchas)
The non-obvious calls an implementer must honor (e.g. fail-closed tenant, banker's rounding,
determinism seed, EF query-filter bypass warnings). Reference `03-adr-core-semantics.md` where relevant.

## API contract
Endpoints (from `api/openapi.yaml`) to add/extend — edit the contract FIRST, regenerate FE types.

## Data model / migration
Entities, columns, FKs, indexes, EF config; migration name.

## Acceptance criteria (Given/When/Then)
Concrete, testable scenarios. Include failure/edge cases and the relevant PRD edge-cases (§20).

## Tests to write
Unit / integration (Testcontainers Postgres) / architecture / e2e, and which `spec/test-vectors/*` to assert.

## Files to create / modify
Explicit paths.

## Guardrails (must hold)
Tenancy isolation (NFR-024), money minor units (BR-008), determinism (NFR-018), concurrency (NFR-023),
module boundaries (NFR-001), UTC (NFR-022), no type suppression.

## Out of scope
What this step explicitly does NOT do (prevents scope creep).

## Definition of Done
AGENTS.md §8 + step-specific checks + `spec/requirements.yaml` updated.
```

## 6. Conventions
- **Commits:** Conventional + gitmoji, reference FR/NFR IDs (AGENTS.md §9). Author = repo owner; no AI attribution.
- **Contract-first** always (AGENTS.md §7). **Guardrail tests must stay green** on every step.
- **Tenant isolation, money-type, and module-boundary** guardrail tests are extended (not weakened) by each relevant step.
