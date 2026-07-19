# Step 03 — ADR: recompute, concurrency, outbox & tie-break semantics

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** —
- **Unblocks:** 04, 15, 16, 17 (and de-risks 18–19)
- **Requirements:** BR-104, FR-095, FR-058, FR-062, NFR-018, NFR-023, §16; edge-cases E-08, E-21

## Goal
Produce a short **Architecture Decision Record** (design only, no product code) that settles the four hard problems the PRD describes at slogan level, so downstream steps implement one agreed model instead of improvising.

## Context & why
The PRD leaves these under-specified; different implementers would resolve them differently, producing inconsistent aggregates and failure modes. Deciding once, early, is cheap; deciding late is a rewrite.

## Design notes (decisions to make & record)
Write `docs/adr/0001-core-semantics.md` answering each with a concrete, testable rule:

1. **Result-edit recompute cascade (BR-104, FR-095, E-08, E-21):**
   - Are standings/advancement/payouts **persisted** or **recomputed-on-read**? (Recommend: persisted derived state + deterministic recompute function.)
   - Is recompute **synchronous in the same transaction** or **async via outbox**? Define the boundary and idempotency.
   - What happens editing a result in a **Completed** tournament (auto-reopen? admin-only? audited)?
   - Effect on **already-approved/paid payouts** (block? void+recreate? manual correction?).

2. **Concurrency conflict semantics (NFR-023):** define expected behavior + status for concurrent: season activation, bracket generate/regenerate, org ownership transfer, tournament cancel/reopen, payment/payout status changes. (Which use `If-Match`; which use domain guards.)

3. **Outbox / realtime delivery (§16, FR-141, FR-060–064):** state the guarantee = **at-least-once** (not exactly-once); event **ordering key** (per resource + monotonic version); **dedupe/idempotency** rule for consumers; **replay/reconnect** = snapshot-then-resume; how clients reconcile stale snapshots (version compare).

4. **Tie-break PRNG (FR-057, NFR-018):** define the exact deterministic algorithm and **seed derivation** for the `random` fallback (e.g. stable hash of `(rng_seed, participantId)` sorted) so results are reproducible and cross-language stable; specify precedence between deterministic fallback and optional manual resolution (E-06) — which is authoritative and how overrides are audited.

## API contract
None (design doc).

## Data model / migration
None (informs later migrations: derived-state tables, outbox table, event version columns).

## Acceptance criteria (Given/When/Then)
- Given the ADR, When an implementer reads it, Then each of the 4 topics has an unambiguous rule with at least one worked example and the associated invariants/tests to write.
- Given the ADR, Then it references the concrete FR/NFR/BR and the `spec/test-vectors/` it constrains.

## Tests to write
None here; the ADR **lists** the tests each downstream step must add (recompute cascade test, concurrency conflict tests, outbox at-least-once/dedupe test, tie-break determinism property test).

## Files to create / modify
- `docs/adr/0001-core-semantics.md`.
- Update `plan/15`, `plan/16`, `plan/17`, `plan/18` references to point at this ADR (already referenced).

## Guardrails (must hold)
Determinism (NFR-018) and concurrency (NFR-023) definitions here become the source of truth other steps must satisfy.

## Out of scope
Implementation. Realtime infra (Step 17). Payment provider specifics (Step 22).

## Definition of Done
ADR reviewed/accepted; each downstream step's "Design notes" is consistent with it; no open questions remain on the 4 topics.
