# Step 08 — Invitations

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 06, 04
- **Unblocks:** 09, 10
- **Requirements:** FR-014, FR-015, FR-016, FR-017, BR-012; §10.3 (Invitation State Machine)

## Goal
Implement the invitation system: inviting users to leagues or organizations by email or link, with a 14-day TTL, and automatic resolution for non-registered users.

## Context & why
Leagues are communities. Users need a way to bring others in without manual account creation by admins. This uses the Invitation state machine (§10.3) and the transactional outbox (Step 04) to ensure invites are sent reliably.

## Design notes (decisions & gotchas)
- **States:** `pending` → `accepted` | `declined` | `revoked` | `expired`.
- **TTL:** 14 days default (A-005). Checked on acceptance.
- **Non-registered Users (FR-017):** If an invite is sent to an email not in `AspNetUsers`, the invite remains `pending`. Upon registration (Step 05), the system must check for pending invites for that email and present them.
- **Role Grant:** Accepting an invite MUST grant exactly the role specified (Organizer/Player) in the specific scope (League/Org).
- **Outbox Emission:** Creating an invite emits an `InvitationCreated` domain event, which Step 09 will pick up to send the actual email.

## API contract
- `POST /leagues/{id}/invitations`: Create an invite.
- `GET /invitations/{id}`: Publicly check invite status (for link-sharing).
- `POST /invitations/{id}/accept`: Transitions state and grants role.
- `POST /invitations/{id}/decline`: Transitions state.

## Data model / migration
- `Invitations`: `id`, `organization_id`, `email`, `scope_type`, `scope_id`, `role`, `state`, `invited_by_user_id`, `expires_at`, `version`.
- Migration: `AddInvitations`.

## Acceptance criteria (Given/When/Then)
- Given a pending invite, When 15 days pass, Then its state is `expired` and acceptance fails.
- Given an invite to `email@example.com` (not a user), When that user registers, Then the invite is linked and can be accepted.
- Given an invitation, When accepted, Then a `Membership` (Step 06) is created for that user/scope/role.
- Given a revoked invite, When acceptance is attempted, Then 403 Forbidden.

## Tests to write
- **Unit**: Invitation state machine transitions; Expiry logic.
- **Integration (Postgres)**: Resolve-on-signup flow; Role-grant verify; Tenant isolation (invite must belong to creator's org).
- **Architecture**: No cross-tenant invitations (NFR-024).

## Files to create / modify
- `src/TourneyHub.Domain/Identity/Invitation.cs`.
- `src/TourneyHub.Application/Identity/Commands/InviteUserHandler.cs`.
- `src/TourneyHub.Infrastructure/Persistence/Configurations/InvitationConfiguration.cs`.
- `src/TourneyHub.Api/Controllers/InvitationsController.cs`.

## Guardrails (must hold)
Tenant isolation (BR-012); UTC for `expires_at` (NFR-022); Optimistic concurrency (NFR-023); No double-acceptance.

## Out of scope
Multi-use links / max-acceptance caps (V1 FR-018); In-app notification bell (Future).

## Definition of Done
AGENTS.md §8; Resolve-on-signup integration test green; Invitation FSM covered by unit tests; `requirements.yaml` updated.
