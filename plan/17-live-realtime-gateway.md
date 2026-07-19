# Step 17 — Live/realtime gateway

- **Scope:** MVP*
- **Status:** ⬜ not started
- **Depends on:** 04, 16
- **Unblocks:** —
- **Requirements:** FR-060, FR-061, FR-062, FR-063, FR-064, §16, NFR-006, NFR-007

## Goal
Implement a realtime notification gateway using SignalR and a Redis backplane. This provides live updates for brackets, standings, and match results, scoped strictly to the organization boundary.

## Context & why
Competitions are exciting because they are live (FR-060). Users shouldn't have to refresh to see progress. The gateway must be secure (no cross-org leak) and scalable across multiple server instances (NFR-007).

## Design notes (decisions & gotchas)
- **SignalR + Redis:** Use the SignalR Redis backplane for horizontal scalability.
- **Group Authorization (FR-064):** Users join groups like `org:{orgId}:tournament:{id}:public`. Middleware MUST verify the user has access to that organization and tournament before allowing the group join.
- **Outbox Consumer (Step 04):** A background service consumes the `Outbox` and broadcasts relevant domain events (e.g. `MatchResultEntered`) to the appropriate SignalR groups.
- **Snapshot-on-Reconnect (ADR 03):** When a client reconnects, it receives a "current state" snapshot plus a version number to reconcile any missed updates.
- **Polling Fallback (FR-063):** The frontend client MUST fallback to HTTP polling if WebSocket/SSE fails.

## API contract
- `/hubs/competition`: SignalR Hub endpoint.
- Authorization: Bearer token (JWT) or Cookie for authenticated; anonymous allowed for public tournament groups.

## Data model / migration
- No new DB entities; depends on `Outbox` (Step 04) and Redis for backplane.

## Acceptance criteria (Given/When/Then)
- Given a public tournament, When a result is entered, Then a spectator on the public page sees the update within 2 seconds (NFR-006) without refreshing.
- Given an organizer in Org A, When they join a realtime group, Then they MUST NOT receive any events from Org B (FR-064).
- Given a network disconnect, When the client reconnects, Then it receives the latest state and version to ensure consistency (ADR 03).

## Tests to write
- **Integration:** `RealtimeHubTests` verifying group authorization and cross-org isolation.
- **E2E (Playwright):** Verify live UI update when a result is patched via API.
- **Load Test:** Verify SignalR broadcast doesn't spike CPU under NFR-005 scale.

## Files to create / modify
- `src/TourneyHub.Api/Hubs/CompetitionHub.cs`.
- `src/TourneyHub.Infrastructure/Realtime/SignalRNotificationService.cs`.
- `src/TourneyHub.Infrastructure/Background/OutboxProcessor.cs`.

## Guardrails (must hold)
Tenant isolation (NFR-024); live latency (NFR-006); secure group naming.

## Out of scope
In-app engagement notifications (Future); chat/social features (Future).

## Definition of Done
AGENTS.md §8; SignalR group auth verified; outbox-to-realtime fan-out working; polling fallback tested; `requirements.yaml` updated.
