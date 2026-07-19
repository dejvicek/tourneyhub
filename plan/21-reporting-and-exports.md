# Step 21 — Reporting & exports

- **Scope:** V1
- **Status:** ⬜ not started
- **Depends on:** 16, 19
- **Unblocks:** —
- **Requirements:** FR-073, FR-076, FR-077, FR-078, FR-100, FR-101, FR-103, BR-107

## Goal
Deliver the depth required for organizers: financial reconciliation reports, CSV exports of all data, and a flexible refund system. This includes custom prize distribution percentages (FR-073) and enforcing the "refund ≤ paid" rule (BR-107/E-17).

## Context & why
MVP finance (Step 18-19) is about tracking the flow. V1 (Step 21) is about reconciliation and flexibility. Organizers need to export data for local analysis (CSV) and handle the "unhappy path" of registrations (refunds/forfeits). Reports must reconcile income (fees) against liabilities (prize pool/payouts) to show the organization's balance (FR-078).

## Design notes (decisions & gotchas)
- **Financial Reconciliation:** `Organization Balance = Σ(Payments) - Σ(Refunds) - Σ(Paid Payouts)`.
- **Refund Logic (BR-107):** A refund record MUST link to a specific `Payment` (or Registration total) and verify the requested amount does not exceed `TotalPaid - TotalRefunded`.
- **CSV Generation (FR-103):** Use a streaming CSV library to avoid memory pressure on large exports. Defer to an async job + outbox notification if the dataset > 5000 rows.
- **Prize Distribution:** Allow custom JSON configuration for rank % (e.g., `[50, 30, 20]`).

## API contract
- `GET /api/v1/tournaments/{id}/reports/financial`: JSON reconciliation data.
- `GET /api/v1/tournaments/{id}/export/csv`: Streamed CSV of standings/rosters/finance.
- `POST /api/v1/registrations/{id}/refunds`: Record a refund (organizer only).

## Data model / migration
- **Tournament:** Add `customPrizeDistribution` (JSONB column).
- **Refund:** New table `refunds(id, payment_id, org_id, amount_minor, reason, recorded_by, occurred_at)`.
- Migration: `Finance_Reporting_And_Refunds`.

## Acceptance criteria (Given/When/Then)
- Given a registration with 1000 cents paid, When an organizer attempts a 1500 cent refund, Then the request is rejected (BR-107, E-17).
- Given a financial report, When computed, Then `income - fees - payouts == balance` matches exactly down to the minor unit.
- Given a large tournament (256+ participants), When a CSV export is requested, Then it returns a valid RFC 4180 file containing all rosters.
- Given a custom 60/40 prize distribution, When the tournament completes, Then payouts generate exactly according to those percentages.

## Tests to write
- **Integration**: `RefundValidationTests` (assert BR-107); `ReportReconciliationTests` (assert vectors where total entries - fees == prize pool).
- **Unit**: `PrizeDistributionTests` (banker's rounding on custom percentages).
- **E2E**: Complete flow: Paid Registration -> Refund -> Verify prize pool reduction.

## Files to create / modify
- `src/TourneyHub.Domain/Finance/Refund.cs`.
- `src/TourneyHub.Application/Finance/GetFinancialReportHandler.cs`.
- `src/TourneyHub.Application/Reporting/ExportCsvHandler.cs`.
- `src/TourneyHub.Domain/Finance/PrizePoolCalculator.cs` (add custom % support).

## Guardrails (must hold)
Tenancy isolation (NFR-024); Money minor units (BR-008); Refund limit (BR-107); UTC (NFR-022).

## Out of scope
PDF Generation (Future FR-102); Automated bank transfers (Step 22).

## Definition of Done
AGENTS.md §8; financial reports reconcile exactly; CSV export functional for large sets; `requirements.yaml` FR-073/076/078/100/101 updated.
