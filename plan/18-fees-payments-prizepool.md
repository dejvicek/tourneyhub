# Step 18 — Fees, payments & prize pool

- **Scope:** MVP*
- **Status:** ⬜ not started
- **Depends on:** 12, 16
- **Unblocks:** 19, 21, 22
- **Requirements:** FR-070, FR-071, FR-072, FR-074, FR-079, FR-080, FR-081, FR-082, BR-005, BR-006, BR-007, BR-008; PRD §10.4

## Goal
Implement tournament entry fees and prize pool calculations with a manual payment ledger. This delivers the financial foundation: registrations track payment status via a state machine (§10.4), and the tournament prize pool is automatically computed using banker's rounding and the "percentage XOR fixed" organizer fee logic (BR-006).

## Context & why
Finance is deferred from the core MVP to V1 for shippability (Plan README §2), but the domain models must support it. Using integer minor units (cents) and a manual provider seam (FR-082) ensures the system is "gateway-ready" without the legal/compliance overhead of real money movement at start. The `ManualProvider` allows organizers to record cash/out-of-band payments today.

## Design notes (decisions & gotchas)
- **Integer minor units only (BR-008):** Use .NET `decimal` for intermediate compute, but all persisted values and API DTOs use `long amount_minor`. Never `double`/`float`.
- **Banker's rounding:** Use `MidpointRounding.ToEven` for all fee/pool splits.
- **Single currency (BR-007):** A tournament's `currency` is immutable once a fee is set; registrations must match this currency (E-18).
- **Payment state machine:** Follow §10.4 strictly. `paid` status is required for entry into the prize pool.
- **PaymentProvider Seam (FR-082):** Define `IPaymentProvider` in Application; implement `ManualProvider` in Infrastructure. Domain logic calls the abstraction.

## API contract
- `PATCH /api/v1/tournaments/{id}/finance`: Set `entryFee`, `currency`, and `feeConfig`.
- `GET /api/v1/tournaments/{id}/registrations`: Include `paymentStatus`.
- `POST /api/v1/registrations/{id}/payments`: Record a manual payment (organizer only).

## Data model / migration
- **Tournament:** Add `currency` (ISO string), `entryFeeMinor` (long), `organizerFeeType` (enum: Fixed/Percentage), `organizerFeeValue` (decimal).
- **Registration:** Add `paymentStatus` (enum), `totalPaidMinor` (long).
- **Payment:** New table `payments(id, registration_id, org_id, amount_minor, currency, status, recorded_by_user_id, occurred_at)`.
- Migration: `Finance_Base_Fees_And_Payments`.

## Acceptance criteria (Given/When/Then)
- Given a tournament with a 10% organizer fee, When 10 players pay a 500 cent entry fee, Then the prize pool is exactly 4500 cents (BR-005, vector "10 paid entries").
- Given a registration, When an organizer records a manual payment, Then the status transitions `Pending → Paid` and the prize pool recomputes.
- Given a tournament in EUR, When a registration is attempted in USD, Then 400 Bad Request (E-18).
- Given a prize pool split that results in a fraction, Then apply banker's rounding per `payout-split.json`.

## Tests to write
- **Unit**: `PrizePoolCalculatorTests` asserting against all cases in `payout-split.json` (gross vs net, fixed vs pct).
- **Integration**: `PaymentFSMTests` (illegal transitions like `Refunded → Paid` rejected); `TenantIsolationTests` (Org A cannot see Org B's payment records).
- **Architecture**: Ensure no `double` or `float` types are used in `TourneyHub.Domain.Finance`.

## Files to create / modify
- `src/TourneyHub.Domain/Finance/Payment.cs`, `PaymentStatus.cs`.
- `src/TourneyHub.Application/Abstractions/IPaymentProvider.cs`.
- `src/TourneyHub.Infrastructure/Finance/ManualProvider.cs`.
- `src/TourneyHub.Domain/Finance/PrizePoolCalculator.cs` (or extend `PayoutSplitter`).
- `api/openapi.yaml` (finance endpoints).

## Guardrails (must hold)
Tenancy isolation (NFR-024); Money minor units (BR-008); UTC (NFR-022); Concurrency (NFR-023) on payment records.

## Out of scope
Actual payout generation (Step 19); Refunds (Step 21); Stripe/Gateway integration (Step 22).

## Definition of Done
AGENTS.md §8; `payout-split.json` prize-pool vectors pass; payment FSM verified; `requirements.yaml` FR-070/071/072/074 updated.
