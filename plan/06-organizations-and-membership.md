# Step 06 — Organizations & membership

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 01, 05
- **Unblocks:** 07, 08, 10
- **Requirements:** FR-150, FR-151, FR-153, FR-154, FR-007, BR-012, BR-013, BR-015; §11 (Permissions)

## Goal
Implement the multi-tenant core: organization creation (self-serve), membership management with role-based access control (RBAC), and server-side active-organization resolution.

## Context & why
TourneyHub is hosted-first and multi-tenant (PRD §1). Every resource belongs to an Organization (FR-151). This step moves from the "identity" of a User to the "context" of an Organization, enabling the authorization layer required for all subsequent features.

## Design notes (decisions & gotchas)
- **Active Org Resolution (FR-154):** Resolved server-side from membership + user preference (claim or `X-Organization-Id`). Middleware must validate the user is an active member of the requested org.
- **Role Invariants (BR-013):** An organization MUST always have ≥1 `OrgOwner`. Transferring ownership requires the recipient to be a member; removing the last owner is blocked.
- **Membership Entity:** Links `User` and `Organization` with a `Role` (OrgOwner, Organizer, Player) and `State` (Active, Suspended).
- **Permissions (§11):** Implement `IAuthorizationHandler` or similar to enforce the RBAC matrix. OrgOwner ⊃ Organizer ⊃ Player.
- **Seeded Org (A-002):** Self-host instances start with one default organization (Step 07 handles bootstrap).

## API contract
- `POST /organizations`: Create org; caller becomes `OrgOwner`.
- `GET /organizations`: List orgs where caller is a member.
- `POST /organizations/{orgId}/transfer-ownership`: Atomic transfer with invariant check.
- `X-Organization-Id` header: Used by clients to switch context (validated server-side).

## Data model / migration
- `Organizations`: `id`, `name`, `slug`, `state`, `plan`, `version`.
- `Memberships`: `user_id`, `organization_id`, `role`, `state`, `joined_at`.
- Migration: `AddOrganizationsAndMemberships`.

## Acceptance criteria (Given/When/Then)
- Given a user who is not a member of Org A, When they send `X-Organization-Id: OrgA`, Then 403 Forbidden.
- Given an OrgOwner, When they attempt to remove themselves as the last owner, Then rejected (BR-013).
- Given a new organization creation, When committed, Then the creator has the `OrgOwner` role and a `Membership` record.

## Tests to write
- **Integration (Postgres)**: Multi-org access isolation (WebApplicationFactory); Ownership transfer invariant.
- **Unit**: RBAC permission check matrix (§11).
- **Architecture**: Enforce `organization_id` FK on all tenant-scoped entities (Step 01 guardrail).

## Files to create / modify
- `src/TourneyHub.Domain/Platform/Organization.cs`, `Membership.cs`.
- `src/TourneyHub.Application/Abstractions/IAuthorizationService.cs`.
- `src/TourneyHub.Infrastructure/Persistence/Configurations/MembershipConfiguration.cs`.
- `src/TourneyHub.Api/Controllers/OrganizationsController.cs`.

## Guardrails (must hold)
Tenant isolation (NFR-024); Server-side resolution only (FR-154); UTC timestamps (NFR-022); Optimistic concurrency on Org (NFR-023).

## Out of scope
Platform-level suspension (Step 07); Invitations (Step 08).

## Definition of Done
AGENTS.md §8; Tenant-isolation test for org-scoped reads green; Role-matrix tests pass; `requirements.yaml` updated.
