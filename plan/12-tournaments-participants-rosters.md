# Step 12 — Tournaments, participants & rosters

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 10
- **Unblocks:** 13, 15, 18
- **Requirements:** FR-040, FR-040a-d, FR-043, FR-044, FR-044a, FR-045, FR-090a, BR-004, BR-004a, §10.3

## Goal
Implement tournament creation and participant registration. This includes team roster assembly (1–10 players), registration window enforcement, and participant uniqueness across a tournament.

## Context & why
Tournaments are the primary unit of competition (FR-040). Registration is a critical FSM (§10.3) that must handle windows, capacity, and roster completeness before a participant is eligible for seeding.

## Design notes (decisions & gotchas)
- **Participant vs User (FR-090a):** A `Participant` is the entity in the bracket. A `ParticipantMember` links a `User` to a `Participant`. In individual play (teamSize=1), there is 1 member.
- **Roster Completeness (BR-004a):** A participant is `Incomplete` until `teamSize` members accept. Only `Confirmed` participants are seeded.
- **Uniqueness (FR-045):** A user cannot be in two participants in the same tournament. Enforce via a unique index on `(tournament_id, user_id)` across all `ParticipantMember` rows.
- **Registration FSM (§10.3):** Transitions: `Open` → `Closed` → `Seeded`.

## API contract
- `POST /tournaments`: Create a tournament (Standalone or Season-bound).
- `GET /tournaments/{id}`: Tournament details.
- `POST /tournaments/{id}/registrations`: Register a participant (Use `Idempotency-Key` from Step 02).
- `POST /participants/{id}/members/accept`: Accept a roster invite.

## Data model / migration
- `Tournaments`: `id`, `organization_id` (FK), `league_id` (optional), `season_id` (optional), `discipline_name`, `team_size`, `result_model`, `score_config` (JSONB), `reg_open_at`, `reg_close_at`, `max_participants`, `status`.
- `Participants`: `id`, `tournament_id` (FK), `captain_id` (FK), `status` (`Incomplete`, `Confirmed`).
- `ParticipantMembers`: `id`, `participant_id` (FK), `user_id` (FK), `status` (`Pending`, `Accepted`).
- Migration: `2024xxxx_AddTournamentsAndParticipants`.

## Acceptance criteria (Given/When/Then)
- Given a tournament with `teamSize=2`, When a captain registers but only one player joins, Then the participant status remains `Incomplete` and cannot be seeded.
- Given a user already registered in Tournament A, When they try to join another team in Tournament A, Then the request is rejected (FR-045).
- Given a registration request, When the same `Idempotency-Key` is used twice, Then only one registration is created (Step 02).

## Tests to write
- **Integration (Postgres):** `TournamentRegistrationTests` covering capacity limits, uniqueness constraints, and the registration FSM (§10.3).
- **Concurrency:** Test concurrent registration at capacity to ensure `max_participants` is not exceeded.

## Files to create / modify
- `src/TourneyHub.Domain/Entities/Tournament.cs`, `Participant.cs`, `ParticipantMember.cs`.
- `src/TourneyHub.Application/Tournaments/*`.
- `src/TourneyHub.Api/Controllers/TournamentsController.cs`.

## Guardrails (must hold)
Tenant isolation (NFR-024); idempotency (Step 02); UTC (NFR-022).

## Out of scope
Seeding and bracket generation (Step 13); result entry (Step 15).

## Definition of Done
AGENTS.md §8; roster completeness logic verified; uniqueness constraint enforced; `requirements.yaml` updated.
