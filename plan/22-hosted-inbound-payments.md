# Step 22 — Hosted inbound payments

- **Scope:** V1 (gated)
- **Status:** ⬜ not started
- **Depends on:** 18
- **Unblocks:** —
- **Requirements:** FR-083, Q-005, Q-005a

## Goal
Implement automated inbound entry-fee collection for the **hosted service** using a single payment provider (e.g., Stripe Checkout). This replaces the manual ledger for supported organizations, making provider webhooks the authoritative source for `Paid`, `Failed`, and `Refunded` statuses.

## Context & why
Manual tracking (Step 18) is the MVP, but the hosted service's value proposition includes handling the "money headache" for Dana (P2). This step swaps the `ManualProvider` for a real gateway. **Crucially, this is GATED on legal review (Q-005a)** regarding money transmission and tax implications for the hosted operator.

## Design notes (decisions & gotchas)
- **Drop-in Adapter (FR-082):** Implement `IPaymentProvider` (from Step 18) using the chosen gateway SDK (e.g., `StripePaymentProvider`).
- **Webhook Authority:** The domain state MUST be updated via webhooks. Idempotency (Step 02) is critical to handle webhook retries.
- **Provider-Scoping:** Only the **hosted instance** enables the gateway. Self-hosted instances remain on `ManualProvider` with a mandatory disclaimer (FR-083).
- **Checkout Flow:** The UI uses the provider's hosted checkout (e.g., Stripe Checkout) to minimize PCI DSS scope.
- **Fail-Closed:** If the provider returns an error or timeout, the registration state remains `Pending`.

## API contract
- `POST /api/v1/registrations/{id}/checkout-session`: Create a hosted checkout session.
- `POST /api/v1/webhooks/payments/{provider}`: Anonymous endpoint for provider callbacks.

## Data model / migration
- **Payment:** Add `externalReference` (nullable string) and `metadata` (JSONB) to track gateway IDs (e.g., Stripe Session ID).
- Migration: `Finance_Gateway_Integration`.

## Acceptance criteria (Given/When/Then)
- Given a hosted organization, When a player registers, Then they are redirected to a secure hosted checkout page.
- Given a successful payment, When the provider webhook is received, Then the registration status transitions to `Paid` and a `Payment` record is created (authoritative source).
- Given a self-hosted instance, When a player registers, Then the manual payment instructions are shown instead of a checkout redirect.
- Given a webhook retry for an already processed payment, Then the system ignores it (idempotency, Step 02).

## Tests to write
- **Integration**: `PaymentWebhookTests` using a mock provider (e.g., Stripe-Mock) to verify the status sync and idempotency.
- **Architecture**: Verify that the domain logic remains independent of the specific provider SDK.
- **Manual**: Verify redirect and "Return to Site" flow on a staging environment.

## Files to create / modify
- `src/TourneyHub.Infrastructure/Finance/StripePaymentProvider.cs` (or chosen provider).
- `src/TourneyHub.Api/Controllers/WebhooksController.cs`.
- `src/TourneyHub.Application/Finance/CreateCheckoutSessionHandler.cs`.
- `web/src/features/finance/CheckoutRedirect.tsx`.

## Guardrails (must hold)
Tenancy isolation (NFR-024); Webhook idempotency (NFR-023); No secrets in logs (NFR-021); Legal gate (Q-005a).

## Out of scope
Outbound payouts (Future); KYC flows (Future); Multiple provider support (Future).

## Definition of Done
AGENTS.md §8; Legal review (Q-005a) signed off; successful end-to-end payment via webhook in test environment; `requirements.yaml` FR-083 updated.
