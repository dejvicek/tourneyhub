# Step 10 — Leagues & seasons

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 06
- **Unblocks:** 11, 12, 16
- **Requirements:** FR-020, FR-021, FR-022, FR-023, FR-024, FR-026, FR-028, FR-029, BR-001, BR-002, BR-003, §10.6, §10.7

## Goal
Implement the core league container and its seasonal lifecycle. This includes CRUD operations with visibility controls (public/unlisted/private), enforcing the "one active season" invariant, and providing immutable snapshots for historical seasons.

## Context & why
Leagues are the top-level container for recurring competition (FR-020). The seasonal model allows standings to reset (FR-024) while preserving history. The visibility model is critical for privacy (private clubs) vs discovery (public leagues).

## Design notes (decisions & gotchas)
- **Tenancy:** Every league and season MUST carry `organization_id`. Resolution must be fail-closed (Step 01).
- **One Active Season (BR-002):** Enforce via a partial unique index `(league_id) WHERE status = 'Active'` or a domain guard.
- **Snapshots (BR-003):** When a season is closed, its final rankings are snapshotted. The season and its rankings become read-only.
- **Visibility (FR-026):** `Unlisted` leagues are excluded from the discovery list but accessible via direct slug/ID.
- **Slug generation:** Leagues need a unique-per-org slug for public URLs (e.g. `/public/leagues/{slug}`).

## API contract
- `POST /leagues`: Create a league.
- `GET /leagues`: List leagues (filtered by visibility/membership).
- `GET /leagues/{id}`: Detailed league view.
- `POST /leagues/{id}/seasons`: Start a new season.
- `GET /public/leagues/{slug}`: Public read-only view (no auth).

## Data model / migration
- `Leagues`: `id`, `organization_id` (FK), `name`, `slug`, `description`, `visibility` (Enum), `owner_id` (FK), `is_archived`.
- `Seasons`: `id`, `league_id` (FK), `name`, `status` (`Draft`, `Active`, `Completed`), `started_at`, `completed_at`, `rng_seed`.
- Migration: `2024xxxx_AddLeaguesAndSeasons`.

## Acceptance criteria (Given/When/Then)
- Given a league with an active season, When I try to start another season in the same league, Then the request is rejected (BR-002).
- Given a private league, When an unauthenticated user tries to view it, Then 404/401 is returned (FR-026).
- Given a completed season, When I try to edit its name or results, Then the action is blocked (BR-003).
- Given a league, When I archive it, Then all write operations on its seasons are blocked (FR-029).

## Tests to write
- **Integration (Postgres):** `LeagueSeasonTests` covering the "one active season" constraint and FSM transitions (§10.7).
- **Architecture:** Ensure `Season` entity does not bypass `OrganizationId` scoping.
- **E2E (Playwright):** Create a league, start a season, verify public page availability for `public` vs `private`.

## Files to create / modify
- `src/TourneyHub.Domain/Entities/League.cs`, `Season.cs`.
- `src/TourneyHub.Application/Leagues/*` (Commands/Queries).
- `src/TourneyHub.Api/Controllers/LeaguesController.cs`, `PublicController.cs`.

## Guardrails (must hold)
Tenant isolation (NFR-024); UTC (NFR-022); immutable `organization_id` (Step 01); concurrency `Version` token (Step 02).

## Out of scope
Scoring configuration (Step 11); actual rankings computation (Step 16); discovery/follow features (MVP*).

## Definition of Done
AGENTS.md §8; FSM transitions for seasons verified; one-active-season invariant enforced; `requirements.yaml` updated.
