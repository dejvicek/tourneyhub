# Step 19 — Payouts & team splits

- **Scope:** MVP*
- **Status:** ⬜ not started
- **Depends on:** 18
- **Unblocks:** 21
- **Requirements:** FR-058, FR-075, FR-075a, BR-004b, BR-008, BR-112; PRD §10.5

## Goal
Generate and manage payouts based on final tournament standings. This wires the existing `PayoutSplitter` to persistence, handling the logic where team prizes are split equally among members with any remainder (rounding leftover) going to the captain (FR-075a, BR-004b).

## Context & why
Tournament completion (Step 16) calculates standings, but the final step is rewarding winners. For team play (`teamSize > 1`), we award points and money to individuals (Q-006). The `PayoutSplitter` domain service already exists and is tested against `payout-split.json`; this step implements the `Payout` and `PayoutShare` entities to track the disbursement lifecycle (§10.5).

## Design notes (decisions & gotchas)
- **Persistence:** A single `Payout` (per-Participant) expands into N `PayoutShare` rows (one per roster member).
- **Team Split (BR-004b):** `base = floor(total / teamSize)`; `captain_share = base + (total % teamSize)`.
- **Status Guard (BR-112):** A payout cannot be marked `Paid` unless the tournament state is `Completed`.
- **Concurrency:** Use `Version` on `Payout` to prevent double-marking as paid if two organizers click simultaneously.
- **Audit:** Every payout status change must emit a domain event to the outbox for auditing.

## API contract
- `GET /api/v1/tournaments/{id}/payouts`: List all calculated payouts and shares.
- `POST /api/v1/payouts/{id}/approve`: Transition `Calculated → Approved`.
- `POST /api/v1/payouts/{id}/mark-paid`: Transition `Approved → Paid` (manual record).

## Data model / migration
- **Payout:** `id`, `org_id`, `tournament_id`, `participant_id`, `rank`, `amount_minor`, `currency`, `status`, `version`.
- **PayoutShare:** `id`, `payout_id`, `user_id`, `amount_minor`, `status`.
- Migration: `Finance_Payouts_And_Shares`.

## Acceptance criteria (Given/When/Then)
- Given a team of 3 wins a 10,000 cent payout, When payouts are generated, Then the captain receives 3334 cents and two members receive 3333 cents (BR-004b, vector "10000 among team of 3").
- Given a tournament is `InProgress`, When an organizer attempts to mark a payout as `Paid`, Then the request is rejected (BR-112).
- Given a payout with 10 shares, When the payout is marked `Paid`, Then all 10 `PayoutShare` rows also transition to `Paid` in the same transaction.
- Given an individual participant (`teamSize=1`), When a payout is generated, Then exactly one `PayoutShare` exists for 100% of the amount.

## Tests to write
- **Unit**: Extend `PayoutSplitterTests.cs` to verify the `Payout` -> `PayoutShare` mapping logic.
- **Integration**: `PayoutLifecycleTests` (enforce §10.5 state machine); `TournamentCompletionIntegration` (assert payouts auto-generate when the final match is saved).
- **Property-based**: Assert `sum(shares) == payout.amount` for random team sizes (2–10) and prize amounts.

## Files to create / modify
- `src/TourneyHub.Domain/Finance/Payout.cs`, `PayoutShare.cs`, `PayoutStatus.cs`.
- `src/TourneyHub.Application/Finance/GeneratePayoutsHandler.cs`.
- `src/TourneyHub.Infrastructure/Persistence/Configurations/PayoutConfiguration.cs`.
- `tests/TourneyHub.Domain.Tests/PayoutSplitterTests.cs` (references `payout-split.json`).

## Guardrails (must hold)
Tenancy isolation (NFR-024); Money minor units (BR-008); No payment before completion (BR-112); UTC (NFR-022).

## Out of scope
Real-time money disbursement via API (Future); Automated KYC/Tax (Future).

## Definition of Done
AGENTS.md §8; `payout-split.json` team-split vectors pass end-to-end; `BR-112` enforced; `requirements.yaml` FR-075/075a updated.
