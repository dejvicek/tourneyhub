# Step 07 — Platform admin & self-host bootstrap

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 06
- **Unblocks:** —
- **Requirements:** FR-009, FR-009a, FR-009b, FR-009c, FR-009d, FR-155, BR-014

## Goal
Establish the platform-operator layer: environment-based bootstrap for the first admin, and the ability for platform operators to suspend/reactivate organizations.

## Context & why
In a self-hosted scenario, someone must be the first admin without a "sign-up" race condition. In a hosted scenario, the operator needs a "kill switch" for abusive tenants. This step provides the global `InstanceAdmin` role and platform-level controls.

## Design notes (decisions & gotchas)
- **Bootstrap (FR-009a):** On startup, if `TOURNEYHUB_ADMIN_EMAIL` is set and no users exist, create/elevate that user. If users exist, only elevate if a valid `TOURNEYHUB_ADMIN_BOOTSTRAP_TOKEN` is provided in a one-time request.
- **One-Shot Bootstrap:** Once an `InstanceAdmin` exists, bootstrap logic MUST disable itself (FR-009c).
- **Organization Suspension (FR-155, BR-014):** A suspended org blocks ALL write requests and is hidden from public lists. This is a platform-level override.
- **Global Role:** `InstanceAdmin` (or PlatformOperator) is a global role, not scoped to a single organization (though they may belong to one).

## API contract
- `PUT /organizations/{orgId}/suspension`: `InstanceAdmin` only; sets `suspended: true/false`.
- Bootstrap: Handled via `Program.cs` / Background service on startup, not a public endpoint (except perhaps a one-time token redemption).

## Data model / migration
- No new tables; `Organization.state` now includes `Suspended`.
- `AspNetRoles`: Add `InstanceAdmin`.

## Acceptance criteria (Given/When/Then)
- Given a fresh instance with `TOURNEYHUB_ADMIN_EMAIL`, When it boots, Then that user is created/elevated as `InstanceAdmin`.
- Given an existing instance with users, When a visitor tries to claim admin via bootstrap, Then rejected unless the secret token is provided.
- Given a `Suspended` organization, When any member tries to `POST /leagues`, Then 403 Forbidden (BR-014).
- Given a `Suspended` organization, When a public visitor lists leagues, Then the suspended org's leagues are hidden.

## Tests to write
- **Integration (Postgres)**: Bootstrap matrix (Fresh vs Existing, Token vs Email); Suspended-org write-block; Last-admin removal block (BR-013/009c).
- **Architecture**: `InstanceAdmin` endpoints are excluded from standard tenant-isolation filters (they are global).

## Files to create / modify
- `src/TourneyHub.Api/Services/BootstrapService.cs` (HostedService).
- `src/TourneyHub.Application/Organizations/Commands/SetSuspensionHandler.cs`.
- `src/TourneyHub.Infrastructure/Identity/InstanceAdminRequirement.cs`.
- `src/TourneyHub.Api/Program.cs` (Register bootstrap).

## Guardrails (must hold)
Fail-closed; ≥1 InstanceAdmin at all times (FR-009c); Suspension blocks writes server-side (BR-014); Audit bootstrap events (FR-120).

## Out of scope
Hosted billing/plans (V1); Fine-grained platform permissions (MVP is binary InstanceAdmin).

## Definition of Done
AGENTS.md §8; Bootstrap verified in logs + DB; Suspension blocks proven by integration test; `requirements.yaml` updated.
