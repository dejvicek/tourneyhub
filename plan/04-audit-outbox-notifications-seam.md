# Step 04 — Audit log + transactional outbox + notification seam

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 01, 03
- **Unblocks:** 08, 09, 15, 16, 17 (events, notifications, live)
- **Requirements:** FR-120, FR-121, FR-122, FR-140, FR-141, FR-143, NFR-017; §16, §18 (outbox)

## Goal
Provide the shared eventing spine: an append-only audit log, a transactional outbox for domain events, and the `INotificationChannel`/`EmailChannel` port — all tenant-scoped — so later steps emit events/notifications/live-updates without reinventing delivery.

## Context & why
Notifications (Step 09), live updates (Step 17), and result recompute (Step 15) all depend on reliable, ordered, at-least-once event publication (per ADR `03`). Building the outbox + audit + channel seam once, correctly, prevents lost/duplicate updates and gives auditability (NFR-017).

## Design notes (decisions & gotchas)
- **Transactional outbox:** domain events are written to an `outbox` table **in the same DB transaction** as the state change (no dual-write). A background dispatcher publishes them at-least-once with a monotonic per-resource version (per ADR `03` §3). Consumers must be idempotent/dedupe.
- **Audit log (FR-120/121):** `AuditEvent` (actor, action, target, before/after, ip/ua, org, at) is **append-only** — no updates/deletes (enforce via DB permissions/trigger or app guard + test). Records security/finance/admin events.
- **Consent (FR-122):** `ConsentRecord(userId, policyVersion, acceptedAt)` captured at registration (used by Step 05/20).
- **Notification seam (FR-141):** `INotificationChannel` (Application port) + `EmailChannel` (Infrastructure). Notifications are triggered by **domain events via the outbox**, not inline, so a failed send never blocks the transaction. Transactional vs engagement distinction (FR-143) — engagement is Future.
- **Tenant-scoped:** outbox, audit, and notifications all carry `organization_id` and respect isolation (Step 01).

## API contract
None user-facing here (audit read views come later, scoped per §11). Internal ports only.

## Data model / migration
Tables: `outbox_messages(id, org_id, type, payload, occurred_at, published_at?, version)`, `audit_events(...)` (append-only), `consent_records(...)`. Indexes on `(published_at IS NULL)` for the dispatcher and `(org_id, target)` for audit.

## Acceptance criteria (Given/When/Then)
- Given a state change that emits an event, When the transaction commits, Then exactly one outbox row exists in the same transaction; if the transaction rolls back, no outbox row exists.
- Given unpublished outbox rows, When the dispatcher runs, Then each is delivered **at least once**, in per-resource version order, and marked published; a redelivery does not duplicate consumer effects (idempotent).
- Given an audit row, When an update/delete is attempted, Then it is rejected.
- Given a domain event mapped to a notification, When published, Then `EmailChannel` is invoked (Mailpit in dev) without blocking the originating transaction.

## Tests to write
- Integration (Postgres): outbox written-in-transaction (commit vs rollback); dispatcher at-least-once + dedupe; audit append-only rejection; notification dispatched via outbox → Mailpit.
- Architecture: audit entities have no update/delete path.

## Files to create / modify
- `src/TourneyHub.Domain/Common/DomainEvent.cs`, `.../Platform/AuditEvent.cs`, `.../Identity/ConsentRecord.cs`.
- `src/TourneyHub.Application/Abstractions/INotificationChannel.cs`, `.../IOutbox.cs`.
- `src/TourneyHub.Infrastructure/Messaging/OutboxDispatcher.cs`, `.../Notifications/EmailChannel.cs`, EF config + migration.
- `tests/TourneyHub.Integration.Tests/*`.

## Guardrails (must hold)
Tenancy (all rows org-scoped, NFR-024); no dual-write (outbox in-transaction); at-least-once + idempotent per ADR; UTC timestamps (NFR-022); no secrets/PII in logs.

## Out of scope
Engagement notifications / extra channels (Future, FR-144); the SignalR gateway itself (Step 17 consumes the outbox); audit UI.

## Definition of Done
AGENTS.md §8; outbox transactionality + audit append-only + notification dispatch tests green (Postgres); `requirements.yaml` FR-120/121/122/140/141, NFR-017 → in_progress.
