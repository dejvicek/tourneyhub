# Step 11 — Scoring system config

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 10
- **Unblocks:** 14, 16
- **Requirements:** FR-025, FR-030, FR-057, NFR-020, §12.1

## Goal
Implement a data-driven scoring engine that converts match results into points. This includes a pure `score(result, config) → points` logic and a registry of ordered tie-breaker rules.

## Context & why
Different disciplines have different scoring rules (e.g., Football 3/1/0, Chess 1/0.5/0). Hardcoding these makes the platform inflexible (NFR-020). A configuration-first approach (PRD §12.1) allows organizers to adapt to any game.

## Design notes (decisions & gotchas)
- **Pure Logic:** The scoring calculator MUST be a pure function with no side effects or DB access. It takes a `MatchResult` and a `ScoringConfig` and returns points earned.
- **Tie-breakers:** Tie-breakers are an ordered list of strategies (e.g., `[Points, HeadToHead, Seed]`).
- **Default Presets:** Implement standard presets (Chess, Football, WinOnly) as static configurations that can be cloned.
- **Validation:** Ensure `allowDraws` is respected. If `allowDraws` is false but a score would result in a draw, the validation should catch it (FR-052).

## API contract
- No new endpoints; `ScoringConfig` is a property of `League` or `Tournament` creation/edit.

## Data model / migration
- `ScoringSystem`: `id`, `organization_id` (FK), `name`, `config` (JSONB: `winPoints`, `drawPoints`, `lossPoints`, `participationPoints`, `allowDraws`).
- `TieBreakerConfig`: Ordered array of tie-breaker types in `League` or `Tournament`.
- Migration: `2024xxxx_AddScoringConfig`.

## Acceptance criteria (Given/When/Then)
- Given a Football scoring config (3/1/0), When a match result is 2-1, Then 3 points are awarded to the winner and 0 to the loser.
- Given a config where `allowDraws` is false, When a 1-1 score is submitted, Then validation fails (FR-052).
- Given two participants with equal points, When tie-breakers are applied, Then they are resolved in the order specified in the config.

## Tests to write
- **Unit:** `ScoringCalculatorTests` asserting against `spec/test-vectors/tie-breaks.json`.
- **Property-based:** `FsCheck` to verify that for any result, if `allowDraws` is false, a draw can never be produced (BR-109).

## Files to create / modify
- `src/TourneyHub.Domain/Logic/Scoring/ScoringCalculator.cs`.
- `src/TourneyHub.Domain/ValueObjects/ScoringConfig.cs`.
- `src/TourneyHub.Infrastructure/Persistence/Configurations/*`.

## Guardrails (must hold)
Determinism (NFR-018); configuration over code (NFR-020).

## Out of scope
Custom scoring UI (V1); ranking recompute logic (Step 16).

## Definition of Done
AGENTS.md §8; unit tests for all presets pass; property-based tests for `allowDraws` pass; `requirements.yaml` updated.
