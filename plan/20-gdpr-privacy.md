# Step 20 — GDPR & privacy

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 05, 16
- **Unblocks:** —
- **Requirements:** FR-008, FR-122, FR-130, FR-131, FR-132, FR-134, FR-135, BR-106; PRD §13

## Goal
Implement the "Privacy by Design" requirements: machine-readable data export (JSON), consent capture at registration, and a "tombstone" account deletion process that anonymizes personal data while preserving competition history (results/standings).

## Context & why
As a hosted service (Decision #2, Q-002), we process personal data and must comply with GDPR. Hard-deleting a user would break historical brackets and league standings (P95 risk RK-04). We solve this by "tombstoning": severing the user link and replacing PII with an anonymous identifier (e.g., "Deleted Player #123"), which preserves the integrity of others' results (Recital 26).

## Design notes (decisions & gotchas)
- **Tombstoning (Decision #2):** Replace `DisplayName`, `Email`, and `Avatar` with generic values. Hard-delete `PasswordHash` and `AuditLog` IP addresses (after 365 days).
- **Integrity:** `Participant` rows link to `User`. On deletion, nullify the `UserId` FK but preserve the `DisplayName` used at the time of the tournament (or "Deleted Player").
- **Sole-Owner Lock (BR-106):** Prevent deletion if the user is the only `OrgOwner` or `LeagueOwner`.
- **Export:** Aggregate data from Identity (Profile), Competition (Registrations/Matches), and Finance (Payments/Payouts) into a single JSON artifact.
- **Consent:** Capture `ConsentRecord` (Plan 04) during Step 05 signup. This step adds the API to query it.

## API contract
- `GET /api/v1/users/me/export`: Returns a full JSON dump of the user's data.
- `DELETE /api/v1/users/me`: Triggers the tombstone/anonymization flow.
- `GET /api/v1/users/me/privacy`: View current visibility and consent status.

## Data model / migration
- No major new tables (uses `ConsentRecord` from Plan 04).
- Add `Visibility` enum to `User` profile (Public/Members/Private).
- Migration: `Identity_Privacy_Hardening`.

## Acceptance criteria (Given/When/Then)
- Given a user with 10 matches played, When they delete their account, Then their name in historical brackets becomes "Deleted Player", but the match results and standings remain unchanged (E-12).
- Given a user who is the only owner of an active League, When they attempt to delete their account, Then the request is rejected with 400 (BR-106).
- Given a user request for export, Then the JSON contains their email, all match scores, and all payment records (FR-131).
- Given a registration flow, When the user has not accepted the latest policy version, Then the registration is blocked (FR-132).

## Tests to write
- **Integration**: `ErasureIntegrityTests` (verify brackets stay intact after user deletion); `ExportCompletenessTests` (assert all modules contribute to the JSON dump).
- **Architecture**: Ensure `AuditLog` PII-scrubbing job is scheduled.
- **Security**: Verify deleted users cannot log in (even if tokens are leaked).

## Files to create / modify
- `src/TourneyHub.Application/Identity/AnonymizeUserHandler.cs`.
- `src/TourneyHub.Application/Identity/ExportUserDataHandler.cs`.
- `src/TourneyHub.Domain/Identity/User.cs` (add Anonymize method).
- `src/TourneyHub.Infrastructure/Persistence/TourneyHubDbContext.cs` (handle null-user FKs).

## Guardrails (must hold)
Tenant isolation (NFR-024); No PII in logs (NFR-021); Competition integrity (FR-130); Sole-owner check (BR-106).

## Out of scope
Legal counsel review (Q-002a); Right-to-rectification (handled by normal Profile Edit).

## Definition of Done
AGENTS.md §8; deletion preserves match history but scrubs PII; JSON export includes participation/finance; `requirements.yaml` FR-008/130/131/132 updated.
