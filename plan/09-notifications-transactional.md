# Step 09 — Transactional notifications

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 04, 05, 08
- **Unblocks:** 15
- **Requirements:** FR-140, FR-141, FR-142, FR-143, NFR-025

## Goal
Implement the delivery of transactional emails (verification, reset, invitations, roster invites) by wiring outbox domain events to the `EmailChannel`, supporting both managed providers and self-host SMTP.

## Context & why
Notifications are the glue of the registration and invitation flows. Per NFR-025, the hosted service needs high-deliverability managed email, while self-hosters need a reliable SMTP path. This step implements the "At-Least-Once" delivery guarantee defined in ADR 03.

## Design notes (decisions & gotchas)
- **Consumer Pattern:** A background worker polls the `outbox` (Step 04), maps `DomainEvents` (e.g., `InvitationCreated`) to email templates, and calls `INotificationChannel.SendAsync`.
- **Idempotency:** Email sends are at-least-once. Use the outbox message ID or a unique `notification_id` to prevent duplicate sends if the background job retries (ADR 03).
- **Fail-Fast SMTP (FR-142):** On startup, the `EmailChannel` MUST validate connectivity (e.g., `QUIT` command to SMTP) and fail-fast if configuration is missing/invalid.
- **Mailpit:** Use Mailpit in local development and CI to verify email content/delivery without real SMTP.
- **Templates:** Use simple Liquid or Razor templates for transactional emails (no marketing/engagement fluff).

## API contract
No public endpoints. Internal implementation of the notification consumer.

## Data model / migration
- No new tables; relies on `outbox_messages` (Step 04).
- May add `sent_notifications` log for troubleshooting (audit).

## Acceptance criteria (Given/When/Then)
- Given a new User registration, When the outbox dispatcher runs, Then a verification email is sent via `EmailChannel`.
- Given an invitation is created, When the dispatcher runs, Then an email with the invite link is sent.
- Given a failed SMTP connection in self-host mode, When the app starts, Then it logs a critical error and fails health checks (NFR-014/025).
- Given a redelivered outbox message, When processed, Then a duplicate email is NOT sent (idempotency).

## Tests to write
- **Integration (Mailpit)**: Trigger registration → Verify email arrives in Mailpit; Trigger invite → Verify link.
- **Unit**: Template mapping logic; Idempotency key generation.
- **Architecture**: Domain events correctly map to transactional templates (FR-143).

## Files to create / modify
- `src/TourneyHub.Infrastructure/Notifications/EmailTemplates/*.liquid`.
- `src/TourneyHub.Infrastructure/Messaging/NotificationOutboxConsumer.cs`.
- `src/TourneyHub.Infrastructure/Notifications/SmtpEmailChannel.cs` (or managed provider impl).
- `src/TourneyHub.Api/Health/SmtpHealthCheck.cs`.

## Guardrails (must hold)
UTC timestamps; No secrets/PII in logs (NFR-021); Fail-fast on invalid config (FR-142); Tenant-scoped notification context (NFR-024).

## Out of scope
Engagement notifications (digests, match-ready) (Future FR-144); Web push / Discord channels (Future).

## Definition of Done
AGENTS.md §8; Mailpit-backed integration tests green in CI; Startup validation for SMTP verified; `requirements.yaml` updated.
