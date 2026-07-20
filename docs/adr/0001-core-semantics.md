# ADR-0001 — Recompute, Concurrency, Outbox & Tie-Break Semantics

- **Status:** Accepted
- **Date:** 2026-07-20
- **Deciders:** Architecture (TourneyHub)
- **Scope:** MVP — informs all downstream competition, finance, and realtime steps
- **References:** BR-104, FR-095, FR-058, FR-062, FR-057, FR-141, FR-060–064, FR-059, NFR-018, NFR-023, E-08, E-10, E-21, PRD §16
- **Test vectors constrained:** `spec/test-vectors/tie-breaks.json` (random fallback), `spec/test-vectors/single-elimination.json` (determinism), `spec/test-vectors/payout-split.json` (recompute determinism)
- **Unblocks:** Steps 04 (audit/outbox/notifications), 15 (match results & recompute), 16 (rankings/standings), 17 (live/realtime), 18 (fees/payments), 19 (payouts)

---

## 1. Result-Edit Recompute Cascade

### 1.1 Persisted Derived State + Deterministic Recompute

**Decision:** Standings, advancement, and payouts are **persisted derived state**, computed by a deterministic, side-effect-free recompute function. They are **never the source of truth** — match results are the source of truth; derived state is always reproducible by re-running the function from source data.

**Rationale:** Persisting derived state enables efficient reads (public standings pages, bracket views) without recomputing on every request. The recompute function remains deterministic so derived state can be verified, replayed, and tested against golden oracles.

**Recompute function contract:**
- **Input:** ordered list of `Match` results within the tournament, the tournament's `formatConfig` and `scoringSystem`, and the tournament's `rng_seed`.
- **Output:** `(Standing[], AdvancementMap, PayoutComputation?)` — a pure function; no database access, no wall-clock, no randomness besides the stored seed.
- **Idempotent:** Running twice with identical inputs produces identical outputs. The function is a mathematical projection of `Matches → DerivedState`.

**How persisting works (write path):**
1. Match result is validated and persisted (optimistic lock check on `Match.version`).
2. Within the **same transaction**, the recompute function is called and its output is `UPSERT`ed into the `Standing`, `Match` (advancement fields), and `Payout` tables.
3. Domain events (for outbox) are emitted after the transaction commits.

**Invariant:** After any result mutation commits, `derivedState == recompute(allMatches, config, rng_seed)` MUST hold. A scheduled integrity check (admin tool) can verify this at any time.

### 1.2 Synchronous vs Async Recompute Boundary

**Decision:** Recompute is **synchronous within the database transaction** for the competition scope (standings, advancement, bracket state). Payout **computation** is also synchronous (the `Payout` rows are upserted). Payout **approval/payment status changes** and notification sends are **not** part of the recompute — they are triggered by domain events via the outbox (see §3).

**Rationale:** Competition integrity requires that after a result edit, standings and bracket advancement are immediately consistent. A tournament must not show "Completed" while standings are stale. Finance state changes (approvals, disbursement records) carry different consistency needs and are better decoupled.

**Boundary:**

| What | How | Transaction boundary |
|---|---|---|
| Match result + advancement + standings | Synchronous recompute | Same DB TX |
| Payout rows (computed amounts) | Synchronous recompute | Same DB TX |
| Payout approval/void/reactivation | Domain event → outbox handler | Separate TX |
| Notification (email/SignalR) | Domain event → outbox → channel | Separate TX |
| Audit event append | Synchronous (part of write TX) | Same DB TX |

### 1.3 Editing a Result in a Completed Tournament

**Decision:** Allowed, **admin/organizer-only**, **always audited**. The tournament's state transitions `Completed → InProgress` automatically (see tournament state machine, PRD §10.1: `Completed → InProgress: reopen for correction (admin, audited)` — FR-059, E-21). This is **not** a separate "reopen" API — editing any result in a `Completed` tournament implicitly reopens it.

**Behaviour:**
1. Write request carries the match's current `version` via `If-Match`.
2. Authorisation check: caller must hold `organizer` or `admin` role on the tournament's org/league.
3. If tournament is `Completed`, auto-transition to `InProgress` (recorded in audit).
4. Result is updated; recompute cascade runs (standings, advancement).
5. Tournament re-evaluates `isComplete()` — if all final matches are resolved again, it transitions back to `Completed`.
6. Audit: `AuditEvent` records `action: "result_edit_completed_tournament"`, `before`, `after`, `actorId`.

### 1.4 Effect on Already-Approved/Paid Payouts

**Decision: Block, do not silently mutate.** When a result edit triggers a recompute that changes payout amounts, already-`Approved` or `Paid` payouts MUST NOT be silently recalculated.

**Behaviour:**
1. During recompute, compare new payout amounts against existing `Payout` rows.
2. If any existing `Payout` is in state `Approved` or `Paid` and its `amount` would change:
   - The recompute still produces the **new** payout calculations, but writes them as `state: "Calculated"` (new rows or updated rows that were only `Calculated`).
   - Existing `Approved`/`Paid` rows are **not mutated** — they are marked `state: "Voided"` with an audit entry and a reference to the replacement `Payout` row.
   - The write returns a **warning** to the caller: `"payouts_require_reapproval"` listing which ranks were affected.
3. The organizer must re-approve the new payout rows. This enforces the payout approval gate (PRD §10.5) and prevents silent financial mutation.

**Invariant:** A `Payout` row in state `Approved` or `Paid` is immutable except for its own explicit state transitions (`Approved → Paid`, or `Approved/Voided` via explicit void action). A recompute never overwrites an approved/paid payout.

---

## 2. Concurrency Conflict Semantics

### 2.1 Mechanism Mapping

| Operation | Mechanism | Rationale |
|---|---|---|
| **Match result edit** | `If-Match` (ETag on `Match.version`) | Direct mutation; two organisers editing the same match must not silently overwrite (NFR-023, E-10). |
| **Registration state change** | `If-Match` (ETag on `Registration.version`) | Concurrent approve/reject/withdraw on same registration. |
| **Payment status change** | `If-Match` (ETag on `Payment.version`) | Must not double-pay or double-refund. |
| **Payout approval/payment** | `If-Match` (ETag on `Payout.version`) | Finance mutations are strictly serialized. |
| **Season activation** | Domain guard (only one `Active` per league, BR-002) + `If-Match` on `Season.version` | The uniqueness constraint is the primary guard; version catch prevents concurrent activation of different seasons for the same league. |
| **Bracket generate/regenerate** | Domain guard (tournament must be `Seeded`, BR-011) + `If-Match` on `Tournament.version` | Regeneration after start is blocked by BR-011 unless force-overridden. The version guard prevents two concurrent generate calls. |
| **Org ownership transfer** | Domain guard (must be ≥1 OrgOwner post-transfer, BR-013) + `If-Match` on `Organization.version` | Two concurrent transfers cannot leave the org with 0 owners. |
| **Tournament cancel/reopen** | Domain guard (valid transitions per state machine, PRD §10.1) + `If-Match` on `Tournament.version` | Enforces legal transitions; version prevents concurrent cancel + reopen. |

### 2.2 Conflict Response

All `If-Match` conflicts return:
- **HTTP 409 Conflict**
- **RFC 7807 Problem Details** with error code `concurrency_conflict`
- Response body includes the current `ETag` (version) so the client can refetch and retry
- The client MUST refetch the resource, reconcile, and re-submit

Domain guard failures return **HTTP 422 Unprocessable Entity** with a domain-specific error code (e.g. `season_already_active`, `bracket_generation_blocked`, `org_owner_required`).

### 2.3 Version Column

Every mutable entity carrying `version` uses it as an EF Core concurrency token (mapped to `xmin` system column on PostgreSQL for zero-overhead optimistic locking, or an explicit `int` column incremented on each write). The version is exposed as the `ETag` header value on GET responses for that resource.

---

## 3. Outbox & Realtime Delivery

### 3.1 Delivery Guarantee: At-Least-Once

**Decision:** The outbox provides **at-least-once** delivery of domain events to consumers (SignalR hub, notification channels). Exactly-once delivery is the consumer's responsibility via idempotency.

**Rationale:** At-least-once is the only guarantee achievable without a two-phase commit between the database and the message broker. The transactional outbox ensures no events are lost; consumers deduplicate.

### 3.2 Event Ordering

**Ordering key:** `(resourceType, resourceId, version)` — monotonic per resource.

- Every domain event carries: `aggregateType` (e.g. `Tournament`), `aggregateId`, `aggregateVersion` (monotonic integer), `eventType`, `timestamp`, `payload`.
- Events for the **same aggregate** are strictly ordered by `aggregateVersion`.
- Events for **different aggregates** have no ordering guarantee (consumers must handle interleaving).

**Outbox table schema:**
```
OutboxEvent: id, aggregateType, aggregateId, aggregateVersion,
             eventType, payload (jsonb), occurredAt (utc),
             publishedAt (utc, nullable), retryCount
```

### 3.3 Deduplication / Idempotency

**Consumer rule:** Process by `(aggregateType, aggregateId, aggregateVersion)` as a deduplication key. If a consumer has already processed event version `V` for aggregate `A`, it MUST ignore re-delivery of the same `(A, V)`.

**How it works:**
- SignalR clients track `lastSeenVersion` per subscription (e.g. per tournament).
- Notification channels track `lastProcessedEventId` to avoid sending duplicate emails.
- On reconnect, clients send their `lastSeenVersion`; the server replays events `> lastSeenVersion`.

### 3.4 Replay & Reconnect

**Snapshot-then-resume pattern:**
1. Client connects (or reconnects after drop) to a SignalR hub group.
2. Client fetches a **full snapshot** of current state via REST (`GET /tournaments/{id}/overview`).
3. Client subscribes to SignalR group and sends its `lastSeenVersion` (from the snapshot's `ETag`/version).
4. Server replays any events with `version > lastSeenVersion` that occurred between the snapshot query and the subscription.
5. Client applies replayed events on top of the snapshot to get to current state.

**Stale snapshot detection (version comparison):**
- Every snapshot response includes a `version` (the tournament's aggregate version at snapshot time).
- Every realtime event carries `aggregateVersion`.
- When a client receives an event with `aggregateVersion > snapshotVersion + 1`, it detects a gap and refetches the snapshot.
- The `overview` endpoint supports `If-None-Match` (ETag) for efficient polling.

**Fallback (polling):** When SignalR transport is unavailable (FR-063), clients poll `GET /tournaments/{id}/overview` with `If-None-Match: <lastEtag>`. The server returns `304 Not Modified` if nothing changed. Poll interval: 5 s default, adaptive backoff to 30s.

### 3.5 SignalR Group Scoping (from PRD §16)

Groups are scoped: `org:{orgId}:tournament:{id}:public` and `org:{orgId}:tournament:{id}:organizer`. Authorization is enforced at group join time (server-side); a client cannot subscribe to another org's channels (NFR-024, FR-064).

---

## 4. Tie-Break PRNG Determinism

### 4.1 Deterministic Algorithm

**Decision:** The `random` tie-breaker (last resort when all configured tie-breakers — headToHead, pointsScored, wins, etc. — are exhausted) uses a **seeded, stable PRNG** applied to a **sorted list of participants**.

**Algorithm:**
1. Input: the set of tied participant IDs, `tieBreakingIndex` (the position of `random` in the tie-breaker list — so different tie groups get different deterministic orders), and the tournament's `rng_seed` (stored `Guid`).
2. Derive a sub-seed: `SHA256(rng_seed || tieBreakingIndex)` — take the first 8 bytes as a `long`.
3. Seed a **splitmix64** PRNG with this `long` value. (Splitmix64 is chosen because it is trivial to implement identically in C# and TypeScript with no platform dependency, unlike `System.Random`.)
4. Sort the participant IDs lexicographically (by `Guid` string representation) to get a stable input order.
5. Fisher-Yates shuffle the sorted list using the splitmix64 PRNG.
6. The resulting shuffled order is the deterministic "random" ranking.

**Why splitmix64:**
- Pure arithmetic (no platform-specific `Random` class). Cross-language reproducibility (C#, TypeScript, Python, SQL) using only 64-bit integer ops.
- Public-domain algorithm. Reference implementation:

```
splitmix64(state):
    state = state + 0x9E3779B97F4A7C15
    z = state
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9
    z = (z ^ (z >> 27)) * 0x94D049BB133111EB
    return z ^ (z >> 31)
```

### 4.2 Seed Derivation

- The tournament's `rng_seed` is a `Guid` stored at tournament creation (generated server-side via `Guid.NewGuid()` — this is the **only** place non-deterministic randomness enters; all subsequent PRNG use derives from this seed).
- `rng_seed` is immutable after tournament creation.
- For tie-breaking, derive sub-seeds deterministically:
  - `subSeed = SHA256(tournament.rng_seed.ToByteArray() || BitConverter.GetBytes(tieBreakingIndex))`
  - Take first 8 bytes of the SHA256 hash as a `long` (big-endian).

### 4.3 Precedence: Deterministic Fallback vs Manual Resolution

**Decision:** The deterministic `random` fallback is **authoritative by default**. An organizer MAY override with a **manual resolution**, which is audited and recorded as an explicit override.

**Behaviour (E-06):**
1. Tie-breakers are applied in order (PRD §12.1: ordered list). When the list reaches `random`, the deterministic splitmix64 shuffle produces a ranking.
2. The tournament's `Standing` rows reflect this deterministic order.
3. **Optional manual override:** if the organizer manually reorders tied participants, the system:
   - Records an `AuditEvent` with `action: "tie_break_manual_override"`, `before` (deterministic order), `after` (manual order).
   - Sets a `tieBrokenManually: true` flag on the affected `Standing` rows.
   - The manual order is the **authoritative** order for display, payouts, and advancement.
4. **Replayability:** The deterministic order is always computable from source data. The manual override is stored explicitly and takes precedence. The integrity check (§1.1) compares derived state against persisted state, flagging differences caused by manual overrides as expected (not errors).
5. **If a result edit changes the tie group makeup** (e.g. a result changes points, breaking the tie differently), any manual override on the old tie group is discarded (audited) and the normal tie-break cascade runs fresh. The organizer must re-apply manual resolution if needed.

**Invariant:** Deterministic computation is always possible and always produces a total order. Manual overrides are transparent, audited, and do not corrupt the ability to recompute.

---

## 5. Tests Required by Downstream Steps

This ADR does not produce tests directly, but it mandates the following test categories:

| Step | Test category | What it verifies |
|---|---|---|
| 15 | Recompute cascade integration | Edit result in Completed tournament → tournament reopens, standings recalculated, payouts voided if approved, audit written. |
| 15 | Recompute determinism property | `recompute(results, config, seed)` called twice with identical inputs → identical outputs. |
| 15 | Recompute idempotency | Running recompute on already-persisted derived state is a no-op (no version bumps, no duplicate audit events). |
| 15 | Concurrency — match result | Two concurrent PATCH to same match → one succeeds, one gets 409. |
| 15 | Concurrency — season activation | Two concurrent POST to activate two seasons → one gets 422 `season_already_active`. |
| 04 | Outbox at-least-once | Event written to outbox table in same TX as domain mutation; publisher eventually delivers (integration test with real Postgres). |
| 04 | Outbox deduplication | Consumer receives same `(aggregateType, aggregateId, aggregateVersion)` twice → processes only once. |
| 17 | Snapshot-then-resume | Client reconnects, fetches snapshot, replays missed events → matches server state. |
| 17 | Stale snapshot detection | Client receives event with version gap → refetches snapshot. |
| 16 | Tie-break determinism property | Same `rng_seed` + same results → same ranking order across multiple runs (property test with FsCheck). |
| 16 | Tie-break cross-language | C# splitmix64 output matches TypeScript splitmix64 output for same seed (validate against golden vectors). |
| 16 | Tie-break manual override | Override recorded, audit written; recompute still produces deterministic order; manual order used for display/payouts. |

---

## 6. Worked Examples

### 6.1 Recompute Cascade (E-08)

**Given:**
- Tournament T has 4 participants, single-elimination, `Completed`.
- Match M3 (semifinal) result: A beat B 21–15.
- Match M4 (final) result: C beat A 21–18.
- Standings: C #1, A #2, B #3, D #4.
- Payout: P1 (rank 1 → $100, Approved), P2 (rank 2 → $50, Approved).

**When:** Organizer edits M3 result: B beat A 21–19 (corrected).

**Then:**
1. `If-Match` header matches M3.version → accepted.
2. Tournament transitions `Completed → InProgress` (auto-reopen). Audit entry `action: "tournament_reopened_for_correction"`.
3. M3.result updated.
4. Recompute: advancement changes → M4 becomes B vs C (not A vs C). M4.result is **invalidated** (state → `Ready`, participants changed). Tournament is no longer complete.
5. Standings recomputed from available results — A and D now tied.
6. Payout: old P1 ($100, rank 1) and P2 ($50, rank 2) were Approved → NOT overwritten. New `Calculated` payout rows created. Old rows marked `Voided` with audit.
7. Response: `200 OK`, body includes `warnings: ["payouts_require_reapproval"]`, tournament state now `InProgress`.

### 6.2 Concurrency — Match Result (E-10)

**Given:** Match M has `version: 5`. ETag: `"5"`.

**When:**
- Organizer Alice sends `PATCH /matches/M/result` with `If-Match: "5"`, setting score 21–15. Succeeds → M.version becomes 6.
- Organizer Bob sends `PATCH /matches/M/result` with `If-Match: "5"`, setting score 15–21.

**Then:** Bob's request fails with:
```
409 Conflict
{
  "type": "https://tourneyhub.dev/errors/concurrency_conflict",
  "title": "Concurrency conflict",
  "detail": "The resource has been modified. Refetch and retry.",
  "currentVersion": "6"
}
```

### 6.3 Outbox — At-Least-Once + Dedup

**Given:** Tournament T has version 3. Match result submitted → version 4.

**When:**
- Transaction commits: `OutboxEvent` row inserted: `(aggregateType: "Tournament", aggregateId: T.id, aggregateVersion: 4, eventType: "match_result_entered", ...)`.
- Publisher picks up the event, delivers to SignalR hub.
- Hub fans out to group `org:{O}:tournament:{T}:public`.
- Publisher crashes before marking event as published → on restart, picks up same event again.

**Then:**
- Client receives event with `aggregateVersion: 4` twice.
- Client's `lastSeenVersion` is already 4 → ignores the duplicate.
- Publisher eventually marks the event `publishedAt = now()` and increments `retryCount`.

### 6.4 Tie-Break PRNG Determinism

**Given:** Tournament with `rng_seed: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"`. Three participants (P-A, P-B, P-C) tied after all non-random tie-breakers. `tieBreakingIndex: 0` (first tie group).

**When:** `random` tie-breaker runs.

**Then:**
1. Sub-seed = `SHA256(rng_seed || tieBreakingIndex)` → first 8 bytes → `long` value.
2. Splitmix64 seeded PRNG produces a deterministic shuffle of `[P-A, P-B, P-C]` (sorted lexicographically first).
3. The **same** output is produced:
   - On the server (C#).
   - On the client (TypeScript, for optimistic display).
   - After a database restore and recompute.
   - On a different OS/architecture.

**Property test:**
```
for all inputs (participantSet, rng_seed, tieBreakingIndex):
    order1 = tieBreakRandom(participantSet, rng_seed, tieBreakingIndex)
    order2 = tieBreakRandom(participantSet, rng_seed, tieBreakingIndex)
    assert order1 == order2
```

---

## 7. Decisions Summary

| # | Topic | Decision |
|---|---|---|
| 1a | Recompute: persist or on-read | Persisted derived state, recomputed synchronously in write TX. |
| 1b | Recompute: sync or async | Synchronous within TX for standings/advancement/payout-calculation; async (outbox) for payout-approval/notifications. |
| 1c | Edit completed tournament result | Allowed (admin/organizer), auto-reopens tournament, audited. |
| 1d | Edit results vs approved payouts | Block mutation of Approved/Paid payouts; void + create new, warn caller. |
| 2a | Match/Registration/Payment/Payout edits | `If-Match` (ETag + version) → 409 Conflict on mismatch. |
| 2b | Season activation, bracket gen, org transfer, tournament state change | Domain guard first (valid transition / invariant), THEN `If-Match` on version. |
| 3a | Outbox delivery | At-least-once; consumers deduplicate by `(aggregateType, aggregateId, aggregateVersion)`. |
| 3b | Event ordering | Per-aggregate monotonic `aggregateVersion`; no cross-aggregate ordering. |
| 3c | Client reconnect | Snapshot-then-resume; version compare for gap detection. |
| 4a | Tie-break PRNG algorithm | Splitmix64 seeded from `SHA256(rng_seed || tieBreakingIndex)`. |
| 4b | Manual override precedence | Override takes precedence over deterministic fallback; override is audited; deterministic order always computable. |
