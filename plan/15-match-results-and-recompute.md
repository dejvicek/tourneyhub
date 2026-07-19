# Step 15 — Match results, validation & recompute

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 02, 03, 13
- **Unblocks:** 16, 18
- **Requirements:** FR-050, FR-051, FR-051a-b, FR-052, FR-054, FR-055, FR-058, FR-062, FR-095, BR-010, BR-103, BR-104, §10.2

## Goal
Implement match result entry with strict validation and the recompute cascade defined in ADR 03. This includes handling forfeits, withdrawals, and organizer overrides with full audit trails.

## Context & why
Result entry is the primary state-change in the competition lifecycle (FR-050). Validating scores and winners (FR-052) and correctly advancing winners in a bracket or updating standings (FR-095) is critical for integrity.

## Design notes (decisions & gotchas)
- **Validation (FR-052):** Validate score ranges, draw policy, and winner consistency before saving.
- **Recompute Cascade (Step 03 ADR):** When a match is completed, the system MUST: 1. Update match status; 2. Advance the winner (if bracket); 3. Recalculate standings; 4. Update season rankings. This MUST be transactional or outbox-consistent.
- **Optimistic Concurrency (Step 02):** Use `If-Match` (ETag/Version) on `PATCH /matches/{id}/result` to prevent lost updates (NFR-023).
- **Match FSM (§10.2):** Valid transitions: `Scheduled` → `InProgress` → `Completed`. Block illegal transitions.

## API contract
- `PATCH /matches/{id}/result`: Submit a result (Requires `If-Match`).
- `POST /matches/{id}/forfeit`: Mark a participant as forfeited.
- `POST /participants/{id}/withdraw`: Withdraw from the tournament.

## Data model / migration
- `Matches`: Add `score_a`, `score_b`, `winner_id`, `forfeited_participant_id`, `version` (Concurrency token).
- `AuditEvents`: Outbox-based audit records for result changes (Step 04).

## Acceptance criteria (Given/When/Then)
- Given a match in a bracket, When the result is entered, Then the winner is automatically placed in the next round's match slot.
- Given a match, When two organizers try to enter different results simultaneously, Then the second one receives a 409 Conflict (Step 02).
- Given a result entry that violates `allowDraws=false`, When submitted, Then the server returns a validation error (RFC 7807).

## Tests to write
- **Integration (Postgres):** `MatchResultTests` covering the FSM transitions and recompute cascade.
- **Concurrency:** Verify 409 Conflict on simultaneous edits.
- **FSM:** Test illegal transitions (e.g. `Completed` → `Scheduled` without override).

## Files to create / modify
- `src/TourneyHub.Application/Matches/Commands/SubmitResult.cs`.
- `src/TourneyHub.Domain/Logic/Recompute/RecomputeService.cs`.
- `src/TourneyHub.Infrastructure/Persistence/TourneyHubDbContext.cs` (concurrency config).

## Guardrails (must hold)
Tenant isolation (NFR-024); concurrency (NFR-023); server authoritative (BR-010); UTC (NFR-022).

## Out of scope
Self-report mode (MVP*); financial payouts (Step 18).

## Definition of Done
AGENTS.md §8; bracket advancement verified; 409 conflict handled; validation matrix passed; `requirements.yaml` updated.
