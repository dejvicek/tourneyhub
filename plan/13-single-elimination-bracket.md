# Step 13 — Single-elimination bracket

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 12
- **Unblocks:** 15
- **Requirements:** FR-046, FR-047, FR-048, FR-053, NFR-018, BR-101, §12.2

## Goal
Implement deterministic single-elimination bracket generation. This includes seeding (random or manual) and automatic assignment of byes to top seeds for non-power-of-two participant counts.

## Context & why
Single-elimination is the core tournament format (FR-041). Generation must be deterministic (NFR-018) so that the same seeds + `rng_seed` always produce the same bracket. Byes must be handled fairly by giving them to top seeds (FR-053).

## Design notes (decisions & gotchas)
- **Determinism (NFR-018):** Use the `rng_seed` stored on the `Season` or `Tournament`. Never use `Random.Shared` or `DateTime.Now`.
- **Bracket Structure:** For $N$ participants, there are $N-1$ matches. The bracket is a tree. Matches are assigned rounds from final (Round 1) back to start.
- **Byes (FR-053):** If $N$ is not a power of 2, the number of byes is $2^{\lceil \log_2 N \rceil} - N$. Byes are assigned to the highest seeds ($1, 2, \dots$).
- **Idempotency (FR-048):** Bracket generation can be repeated until the first match result is entered. After that, it is locked.

## API contract
- `POST /tournaments/{id}/seed`: Set seeds (random or manual).
- `POST /tournaments/{id}/generate-bracket`: Generate the matches.

## Data model / migration
- `Matches`: `id`, `tournament_id` (FK), `round_number`, `position_in_round`, `participant_a_id` (FK, optional for byes), `participant_b_id` (FK, optional), `winner_id` (FK, optional), `status` (`Scheduled`, `InProgress`, `Completed`), `version`.
- Migration: `2024xxxx_AddMatches`.

## Acceptance criteria (Given/When/Then)
- Given 7 participants, When the bracket is generated, Then 1 bye is awarded to the top seed, and there are 6 matches total.
- Given a specific `rng_seed`, When the bracket is generated twice, Then the resulting matches and pairings are identical (NFR-018).
- Given a tournament that has already started (one match completed), When I try to regenerate the bracket, Then the request is blocked (FR-048).

## Tests to write
- **Unit:** `BracketGeneratorTests` asserting against `spec/test-vectors/single-elimination.json` for $N=3, 5, 7, 16$. Assert: correct bye seeds, match tree structure, $N-1$ count, no bye-vs-bye.
- **Property-based:** Verify determinism — `(input, seed) => matches` is a pure function.

## Files to create / modify
- `src/TourneyHub.Domain/Logic/Formats/SingleEliminationGenerator.cs`.
- `src/TourneyHub.Application/Tournaments/Commands/GenerateBracket.cs`.

## Guardrails (must hold)
Determinism (NFR-018); tenant isolation (NFR-024).

## Out of scope
Round-robin format (Step 14); match result entry (Step 15).

## Definition of Done
AGENTS.md §8; asserts against `single-elimination.json` pass; determinism property verified; `requirements.yaml` updated.
