# Step 05 — Auth & accounts

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 00, 01, 02
- **Unblocks:** 06, 08, 09, 20
- **Requirements:** FR-001, FR-002, FR-003, FR-004, FR-005, FR-010, FR-013, NFR-009, BR-009

## Goal
Implement the core identity lifecycle: self-registration with password policy, email verification gate, JWT-based login (access + refresh), and password reset — governed by the account-state machine (§10.8).

## Context & why
Identity is the root of accountability. Per BR-009, verification is a mandatory gate before a user can organize competitions or handle money. We use ASP.NET Core Identity but must harden it with Argon2id and k-anonymity breached-password checks to meet NFR-009.

## Design notes (decisions & gotchas)
- **Hashing:** Argon2id (preferred) or PBKDF2 with high iterations (ASP.NET Core Identity default).
- **Password Policy:** Min 12 chars; use a k-anonymity API (e.g., HaveIBeenPwned) to block breached passwords (R-001).
- **Enumeration Defense:** Password reset and registration MUST NOT leak account existence. Reset always returns `202 Accepted`.
- **States (§10.8):** `pending_verification` (default) → `active` (on verify). `suspended`/`banned` block all tokens.
- **Verification Gate:** Implement a policy/guard that checks `EmailConfirmed && State == Active` for sensitive operations (FR-004, BR-009).
- **Rate Limiting:** Apply Step 02's rate limiter to all `/auth/*` endpoints.

## API contract
- `POST /auth/register`: Creates account, captures `consentPolicyVersion` (FR-146/122), emits `UserRegistered` event.
- `POST /auth/login`: Issues `TokenPair`.
- `POST /auth/verify-email`: Validates token, transitions state to `active`.
- `POST /auth/password-reset`: Handles both request (email) and completion (token + new password).

## Data model / migration
- `AspNetUsers` extensions: `state` (enum), `display_name`, `avatar_url`, `locale`, `timezone`, `last_login_at`.
- `ConsentRecords` (Step 04) linked to User.
- Migration: `AddIdentityAndAccountStates`.

## Acceptance criteria (Given/When/Then)
- Given a registration with a common password (e.g., `Password123!`), When submitted, Then rejected by breached-password check.
- Given a newly registered user, When they try to create a league, Then 403 Forbidden until email is verified (BR-009).
- Given a password reset request for a non-existent email, When submitted, Then 202 Accepted (no enumeration).
- Given a `suspended` user, When they attempt to login or use an active JWT, Then 401/403.

## Tests to write
- **Unit**: Password policy (length, breached); Account state machine valid/invalid transitions.
- **Integration (Postgres)**: Registration → Verification → Capability unlock; Login rate limiting; Token refresh rotation.
- **Architecture**: Ensure no empty `catch` in auth flows; no secrets in logs (NFR-021).

## Files to create / modify
- `src/TourneyHub.Domain/Identity/User.cs` (state, display name).
- `src/TourneyHub.Infrastructure/Identity/BreachedPasswordValidator.cs`.
- `src/TourneyHub.Api/Controllers/AuthController.cs`.
- `src/TourneyHub.Application/Identity/*` (Commands/Handlers).

## Guardrails (must hold)
UTC for `last_login_at` (NFR-022); No type-safety suppression; No secrets in logs; Argon2id/high-iteration PBKDF2 (NFR-009).

## Out of scope
OAuth/Social login (V1 FR-011); 2FA (V1 FR-012); Organization creation (Step 06).

## Definition of Done
AGENTS.md §8; verification-gate proven by test; k-anonymity check active; `requirements.yaml` updated.
