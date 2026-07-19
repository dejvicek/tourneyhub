# Step 16 — Rankings, standings & public reads

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 11, 15
- **Unblocks:** 17, 18, 20
- **Requirements:** FR-030, FR-058, FR-090, FR-090a, FR-091, FR-092, FR-093, FR-094, FR-095

## Goal
Implement tournament standings (participant-based) and league/season rankings (user-scoped). This step fixes the contract mismatch by providing per-player crediting for team play and immutable season snapshots.

## Context & why
Tournament standings show who won a specific event (FR-058). League rankings aggregate performance across many events. PRD FR-090a requires that in team play, points are awarded to users individually, allowing for personal leaderboard progress regardless of ad-hoc partners.

## Design notes (decisions & gotchas)
- **Standing Split:** Fix `api/openapi.yaml` to distinguish between `TournamentStanding` (Participant-scoped) and `SeasonRanking` (User-scoped).
- **Per-Player Crediting (FR-090a):** When a Participant (Team) earns points, iterate over its `ParticipantMembers` and add those points to each user's `SeasonRanking` entry.
- **Immutability (FR-091):** Once a season is `Completed`, its rankings MUST be snapshotted and never changed.
- **Derived State:** Persist standings in the database for performance (ADR 03); recompute only on match result changes.

## API contract
- `GET /tournaments/{id}/standings`: Current participant standings.
- `GET /seasons/{id}/rankings`: Current user-scoped rankings for the season.
- `GET /public/tournaments/{slug}/overview`: Public read-only composite view.

## Data model / migration
- `TournamentStandings`: `id`, `tournament_id`, `participant_id`, `points`, `wins`, `losses`, `draws`, `rank`.
- `SeasonRankings`: `id`, `season_id`, `user_id`, `points`, `matches_played`, `rank`.
- `RankingSnapshots`: Serialized historical rankings per completed season.
- Migration: `2024xxxx_AddRankingsAndSnapshots`.

## Acceptance criteria (Given/When/Then)
- Given a 2v2 tournament, When a team wins a match, Then both players in that team receive the match points in their individual season ranking (FR-090a).
- Given a completed season, When its matches are edited (via admin override), Then the historical snapshot remains unchanged (FR-091).
- Given a tournament, When a match result is updated, Then the tournament standings and season rankings are recomputed deterministically.

## Tests to write
- **Integration (Postgres):** `RankingRecomputeTests` asserting correct point distribution for team play.
- **Architecture:** Verify that `SeasonRanking` records are isolated by `OrganizationId`.
- **Performance:** Ensure standing/ranking reads do not require recomputing the whole history (use persisted state).

## Files to create / modify
- `api/openapi.yaml` (Update `Standing` model split).
- `src/TourneyHub.Domain/Entities/TournamentStanding.cs`, `SeasonRanking.cs`.
- `src/TourneyHub.Application/Rankings/Queries/*`.

## Guardrails (must hold)
Tenant isolation (NFR-024); determinism (NFR-018); no cross-org leak.

## Out of scope
Live push (Step 17); finance (Step 18).

## Definition of Done
AGENTS.md §8; per-player crediting verified; season snapshots working; `requirements.yaml` updated.
