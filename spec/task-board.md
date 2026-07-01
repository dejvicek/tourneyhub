# TourneyHub — Vertical-Slice Task Board

> The execution plan for building TourneyHub with AI agents. Work ONE slice at a time,
> in order. Each slice is a small, independently-verifiable unit (≈1 PR) mapped to FR/NFR
> IDs, with Given/When/Then acceptance and the exact tests to write. This is the "what to
> build next" companion to `spec/requirements.yaml` (coverage) and `api/openapi.yaml` (contract).
>
> **How to work a slice** (see AGENTS.md §6): read the linked FRs + test-vectors → write the
> failing tests → implement the minimum → verify (build/test/lint/openapi/migration) → update
> `spec/requirements.yaml` → commit. Keep it atomic; if a slice needs more than a few files, split it.
>
> Status: ⬜ not started · 🟨 in progress · ✅ done
> Sequencing follows PRD §26.

---

## Phase 0 — Foundation & tenancy

### S0.1 — Solution scaffold & infra  ✅
- **Delivers:** .NET 8 clean-arch solution, docker-compose (PG/Redis/Mailpit), CI, web SPA, OpenAPI contract, golden test-vectors, guardrail tests.
- **Done.** (Tiers 1–3 to date.)

### S0.2 — Tenant data layer & isolation  🟨
- **FR/NFR:** FR-151, FR-152, NFR-004, NFR-024
- **Delivered:** `TenantEntity`, `Organization`, `League`, `ITenantContext`, DbContext global query filter + SaveChanges stamping/guard, `InitialCreate` migration, isolation test harness.
- **Remaining:** wire `ITenantContext` implementation in the API (resolve org from the authenticated principal / active-org header) + `AddDbContext` in `Program.cs`; add a Postgres-backed migration-apply test in CI.

### S0.3 — Audit log seam  ⬜
- **FR/NFR:** FR-120, FR-121, NFR-017
- **Depends on:** S0.2
- **Acceptance:**
  - Given any state-changing domain action, When it commits, Then an append-only `AuditEvent` (actor, action, target, before/after, ip/ua, org) is recorded.
  - Given an audit row, When any update is attempted, Then it is rejected (append-only).
- **Tests:** integration — a sample write produces exactly one audit row scoped to the org; attempted mutation throws.

---

## Phase 1 — Identity & organizations

### S1.1 — Registration, verification, login, reset  ⬜
- **FR/NFR:** FR-001, FR-002, FR-003, FR-004, FR-005, FR-010, NFR-009
- **Endpoints:** `POST /auth/register`, `/auth/login`, `/auth/verify-email`, `/auth/password-reset`
- **Acceptance:**
  - Given a new email+password (≥12 chars), When registering, Then a `pending_verification` account is created and a verification email is queued (Mailpit in dev).
  - Given an unverified account, When calling an organize/finance action, Then it is blocked (BR-009).
  - Given a valid verification token, When posting it, Then the account becomes `active`.
  - Given valid credentials on an active account, When logging in, Then an access+refresh token pair is issued.
  - Given a reset request, Then the response is always 202 (no account enumeration).
- **Tests:** integration (Testcontainers/SQLite) for each transition; state-machine test rejecting illegal transitions (§10.8); password-policy unit tests.

### S1.2 — Organization onboarding  ⬜
- **FR/NFR:** FR-150, FR-153, FR-154, FR-007
- **Endpoints:** `POST /organizations`, `GET /organizations`, `POST /organizations/{id}/transfer-ownership`
- **Depends on:** S0.2, S1.1
- **Acceptance:**
  - Given an authenticated verified user, When creating an org, Then they become its OrgOwner and it is `active`.
  - Given an OrgOwner, When transferring ownership to another member, Then ownership moves and ≥1 OrgOwner always remains (FR-153).
  - Given a user in multiple orgs, When making any write, Then the server resolves exactly one active org (FR-154) — never from client input.
  - Self-host: booting an empty instance seeds exactly one default org (A-002).
- **Tests:** integration for create/transfer; **tenant-isolation** test extended to the new endpoints; "last OrgOwner cannot be removed" test.

### S1.3 — Platform operator & self-host bootstrap  ⬜
- **FR/NFR:** FR-009, FR-009a, FR-009b, FR-009c, FR-009d, FR-155
- **Endpoints:** `PUT /organizations/{id}/suspension`
- **Acceptance:**
  - Given `TOURNEYHUB_ADMIN_EMAIL` set, When the instance boots, Then that user is created/elevated to InstanceAdmin (one-shot, audited).
  - Given `ALLOW_FIRST_USER_ADMIN=true` AND zero users, When the first user registers, Then they become InstanceAdmin; otherwise never.
  - Given the last InstanceAdmin, When removal is attempted, Then it is blocked (always ≥1).
  - Given a platform operator, When suspending an org, Then all writes in that org are blocked and it is hidden from discovery (FR-155, BR-014).
- **Tests:** bootstrap matrix (env/token/first-user/opt-out); suspended-org write-block integration test.

### S1.4 — Invitations & membership  ⬜
- **FR/NFR:** FR-014–017, FR-023, FR-027; permissions §11
- **Endpoints:** `POST /leagues/{id}/invitations`
- **Acceptance:** invite by email/link → states `pending→accepted/declined/revoked/expired` (TTL 14d); accepting grants the invited role only; unknown email resolves on signup.
- **Tests:** invitation state-machine (§10.3-adjacent); authorization-matrix tests (§11).

### S1.5 — Transactional notification seam  ⬜
- **FR/NFR:** FR-140, FR-141, FR-142, FR-143, NFR-025
- **Acceptance:** `INotificationChannel`/`EmailChannel` sends verification, reset, invitations, roster invites, self-report confirmations; triggered by domain events (outbox); hosted uses managed provider, self-host SMTP validated at startup.
- **Tests:** outbox → channel dispatch integration test (Mailpit); startup fails fast on missing SMTP config in self-host.

---

## Phase 2 — Competition core

### S2.1 — Leagues & seasons  ⬜
- **FR/NFR:** FR-020, FR-021, FR-022, FR-024, FR-026, FR-026a, FR-028, FR-028a, FR-029, FR-032; BR-002/003
- **Endpoints:** `GET/POST /leagues`, `GET /leagues/{id}`, `POST /leagues/{id}/seasons`, `GET /public/leagues/{slug}`
- **Acceptance:**
  - Given a league, When starting a new season while one is `active`, Then it is rejected (exactly one active — BR-002) unless the active is closed first.
  - Given a closed season, When read later, Then its ranking snapshot is immutable (BR-003, FR-024).
  - Given visibility `public`/`unlisted`, When fetching the public page unauthenticated, Then it renders; `private` requires membership.
- **Tests:** season state-machine (§10.7); one-active-season invariant; public-page auth matrix; **tenant-isolation** on all new endpoints.

### S2.2 — Scoring system configuration  ⬜
- **FR/NFR:** FR-025, FR-030, NFR-020; §12.1
- **Acceptance:** `score(result, config) → points` is a pure function honoring win/draw/loss/bye/participation points, `allowDraws`, and ordered tie-breakers; presets provided.
- **Tests:** unit tests from `spec/test-vectors/tie-breaks.json` scoring config; property test "draws only when allowed" (BR-109).

### S2.3 — Tournaments, teamSize, participants & rosters  ⬜
- **FR/NFR:** FR-040, FR-040a, FR-040b, FR-040c, FR-040d, FR-043, FR-044, FR-044a, FR-045, FR-090a; BR-004/004a
- **Endpoints:** `POST /tournaments`, `GET /tournaments`, `POST /tournaments/{id}/registrations`
- **Acceptance:**
  - Given `teamSize` 1–10, When registering, Then a Participant needs exactly `teamSize` accepted members before it can be confirmed/seeded (FR-044a).
  - Given a player already in one Participant, When they accept a second roster in the same tournament, Then it is rejected (FR-045, unique `(tournament_id, user_id)`).
  - Given `resultModel=score`, When creating, Then `scoreConfig` (min/max/allowDraws) is captured (FR-040b).
- **Tests:** roster-completeness; duplicate-player rejection (DB unique + idempotency); registration state-machine (§10.3).

### S2.4 — Seeding & Single-Elimination bracket  ⬜
- **FR/NFR:** FR-046, FR-047, FR-048, FR-053, NFR-018; BR-101; §12.2
- **Endpoints:** `POST /tournaments/{id}/seed`, `POST /tournaments/{id}/generate-bracket`
- **Acceptance:** deterministic generation from seeds + stored `rng_seed`; byes to top seeds; regeneration blocked after start unless forced+audited.
- **Tests:** **`spec/test-vectors/single-elimination.json`** (N=3/5/7/16) — exact match on byes, match tree, N−1 count; determinism property test (same seed ⇒ same bracket).

### S2.5 — Round-Robin & tie-breaks  ⬜
- **FR/NFR:** FR-041, FR-057, BR-102; §12.3
- **Acceptance:** N·(N−1)/2 matches, every pair once, one bye/round for odd N; ordered tie-breakers resolve standings deterministically.
- **Tests:** **`round-robin.json`** + **`tie-breaks.json`** golden vectors; property "no participant plays twice in a round".

### S2.6 — Match results, validation & self-report  ⬜
- **FR/NFR:** FR-050, FR-051, FR-051a, FR-051b, FR-052, FR-054, FR-055, FR-058, FR-062, FR-095; BR-010/103/104
- **Endpoints:** `PATCH /matches/{id}/result` (If-Match/ETag)
- **Acceptance:**
  - Given a result, When it violates `resultModel`/`scoreConfig`, Then it is rejected (FR-052).
  - Given `playerSelfReport`, When a captain submits and the opposing captain confirms, Then it finalizes; dispute/timeout routes to the organizer; organizer can always override (FR-051a/b).
  - Given a concurrent edit, When versions mismatch, Then 409 (NFR-023).
  - Given a finalized result edit, Then downstream advancement/standings/payouts recompute (BR-104).
- **Tests:** match state-machine (§10.2); optimistic-locking 409 test; validation matrix; recompute-on-edit.

### S2.7 — Rankings, standings & public live pages  ⬜
- **FR/NFR:** FR-030, FR-058, FR-090, FR-090a, FR-091, FR-092, FR-093, FR-095; FR-060, FR-061, FR-064; §16
- **Endpoints:** `GET /tournaments/{id}/standings`, `GET /tournaments/{id}/overview`
- **Acceptance:** standings computed deterministically; team points credited per-player (FR-090a); closed-season snapshots immutable; live updates pushed to org-scoped SignalR groups, public channels carry only public data (FR-064).
- **Tests:** ranking recompute determinism; **per-player crediting** vector; SignalR group-authorization test (no private leak, no cross-org).

---

## Phase 3 — Finance

### S3.1 — Fees, payments, prize pool  ⬜
- **FR/NFR:** FR-070, FR-071, FR-072, FR-074, FR-079, FR-080, FR-081, FR-082; BR-005/006/007/008
- **Acceptance:** entry fee (minor units + currency); payment status transitions (§10.4); prizePool = Σ(paid) − organizerFee (% XOR fixed); single currency per scope; `IPaymentProvider`/`ManualProvider` seam.
- **Tests:** **`payout-split.json`** prize-pool + rounding vectors; "one currency per scope" rejection; payment state-machine.

### S3.2 — Payouts & team splits  ⬜
- **FR/NFR:** FR-058, FR-075, FR-075a; BR-004b/008/112; §10.5
- **Acceptance:** payout per final standing; team payout split equally, remainder→captain, Σ shares == payout; payouts cannot be `paid` before tournament `completed` (BR-112).
- **Tests:** **`payout-split.json`** team-split vectors (already wired in `PayoutSplitterTests`); payout state-machine; property "Σ payouts == prize pool".

---

## Phase 4 — Hardening (V1)

### S4.1 — GDPR export/delete, consent, retention  ⬜
- **FR/NFR:** FR-008, FR-122, FR-130, FR-131, FR-132, FR-134, FR-135; §13
- **Acceptance:** JSON export of all PII; deletion tombstones identity but retains anonymized match/finance facts (R-006/Q-002); consent captured at registration.
- **Tests:** export completeness; erasure severs User↔Participant while brackets remain intact.

### S4.2 — Reporting + CSV, refunds, configurable prize distribution  ⬜
- **FR/NFR:** FR-073, FR-076, FR-077, FR-078, FR-100, FR-101
- **Tests:** financial report reconciliation; refund ≤ paid (BR-107); custom per-rank distribution vectors.

### S4.3 — Hosted inbound payments (gateway)  ⬜
- **FR/NFR:** FR-083, Q-005/Q-005a; §6.6
- **Acceptance:** one provider collects entry fees; webhooks authoritative for `paid/failed/refunded`; `ManualProvider` remains for self-host. **Gated on legal review (Q-005a).**

---

## Cross-cutting (apply to every slice — enforced by guardrail tests)

- **Tenant isolation** on every new tenant-scoped surface (NFR-024) — extend `TenantIsolationTests`.
- **Module boundaries** (NFR-001) — `ModuleBoundaryTests` must stay green.
- **Money = integer minor units** (BR-008) — `MoneyTypeGuardTests` must stay green.
- **Determinism** where applicable (NFR-018) — cover with the relevant golden vectors.
- **Definition of Done** — AGENTS.md §8. No evidence = not done.
