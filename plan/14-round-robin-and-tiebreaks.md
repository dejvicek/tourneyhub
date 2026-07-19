# Step 14 — Round-robin & tie-breaks

- **Scope:** MVP*
- **Status:** ⬜ not started
- **Depends on:** 11, 12
- **Unblocks:** 16
- **Requirements:** FR-041, FR-057, BR-102, §12.3, NFR-018

## Goal
Implement round-robin schedule generation using the circle method (single or double) and deterministic tie-breaker resolution for standings.

## Context & why
Round-robin ensures every participant plays every other participant (FR-041). Tie-breakers are essential when participants finish with equal points (FR-057). This step provides the pairings and the resolution logic for equal standings.

## Design notes (decisions & gotchas)
- **Circle Method:** Use the standard circle algorithm to generate pairings for $N$ participants. For odd $N$, a "Dummy" participant is used to represent a Bye.
- **Pairing Uniqueness:** No participant plays twice in the same round.
- **Tie-breaker PRNG (Step 03 ADR):** When points and all configured tie-breakers are equal, use a deterministic PRNG based on `(rng_seed, participantId)` to break the tie (NFR-018).
- **Double Round-Robin:** Simply repeat the circle method with home/away slots swapped.

## API contract
- `POST /tournaments/{id}/generate-schedule`: Generate round-robin matches.

## Data model / migration
- No new entities; uses `Matches` and `Tournaments.tie_breaker_config`.

## Acceptance criteria (Given/When/Then)
- Given 4 participants, When a single round-robin is generated, Then 3 rounds of 2 matches each are created.
- Given 5 participants (odd), When a round-robin is generated, Then each participant gets exactly one bye over 5 rounds.
- Given two participants with identical records, When tie-breakers are applied, Then the resolution is deterministic and stable across recomputes (ADR 03).

## Tests to write
- **Unit:** `RoundRobinGeneratorTests` asserting against `spec/test-vectors/round-robin.json` for $N=4, 5$.
- **Unit:** `TieBreakerTests` asserting against `spec/test-vectors/tie-breaks.json`.
- **Property-based:** "No participant plays twice per round" invariant.

## Files to create / modify
- `src/TourneyHub.Domain/Logic/Formats/RoundRobinGenerator.cs`.
- `src/TourneyHub.Domain/Logic/Scoring/TieBreakerResolver.cs`.

## Guardrails (must hold)
Determinism (NFR-018); tenant isolation (NFR-024).

## Out of scope
Single-elimination (Step 13); persistent rankings (Step 16).

## Definition of Done
AGENTS.md §8; asserts against `round-robin.json` and `tie-breaks.json` pass; no duplicate pairings per round; `requirements.yaml` updated.
