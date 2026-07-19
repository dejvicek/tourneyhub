# Step 00 — Project meta & tooling hardening

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** —
- **Unblocks:** everything (quality gates + honest CI)
- **Requirements:** NFR-013, NFR-015, NFR-016, NFR-019, NFR-021, and AGENTS.md §8 (DoD)

## Goal
Make the repo's quality gates real and the licensing correct, so every later step is verified by evidence rather than appearance.

## Context & why
Review found: no `LICENSE` (AGPL-3.0 is Decision #1 for an open-source project), no `.editorconfig`/analyzers/central package management (so "analyzers/format pass" in the DoD has no teeth), CI spins Postgres/Redis that no test uses, migrations are never applied in CI, no dependency/secret scanning, and `/health/ready` returns 200 unconditionally. This step closes those gaps.

## Design notes (decisions & gotchas)
- **License:** add full **AGPL-3.0** text as `LICENSE` (Q-001). Add a short `CONTRIBUTING.md` noting the CLA requirement (NFR-019).
- **Central package management:** introduce `Directory.Packages.props` and move all `PackageReference` versions there (`ManagePackageVersionsCentrally=true`); removes the current EF version-drift class of bugs.
- **Analyzers/format:** add `.editorconfig` (naming/format rules) and enable analyzers; keep `TreatWarningsAsErrors=true`. Do NOT auto-suppress — fix or justify.
- **Real health checks:** `/health/ready` MUST check DB + Redis (use `AddHealthChecks().AddNpgSql(...).AddRedis(...)`); `/health/live` stays a liveness ping.
- **CI must use the services it starts:** the backend job must run at least one Postgres-backed test (see Step 01) and apply migrations (`dotnet ef database update` OR a migrate-on-start test).

## API contract
None. (`/health/*` are host endpoints, may be documented later.)

## Data model / migration
None.

## Acceptance criteria (Given/When/Then)
- Given a fresh clone, When CI runs, Then it: builds, runs tests **including a Postgres-backed integration test**, **applies the EF migration**, runs `dotnet list package --vulnerable` and `npm audit` (fail on high), runs secret scanning, and lints OpenAPI.
- Given the API with a down database, When hitting `/health/ready`, Then it returns 503 (not 200).
- Given a PR that introduces a formatting/analyzer violation, When CI runs, Then the build fails.
- Given the solution, When restoring, Then all package versions resolve from `Directory.Packages.props` with no version-conflict warnings.

## Tests to write
- CI workflow updated (not a unit test, but must be green): jobs for scanning + migration-apply.
- A health-check integration test (down-dependency → unhealthy).

## Files to create / modify
- `LICENSE` (AGPL-3.0 full text), `CONTRIBUTING.md`, `.editorconfig`, `Directory.Packages.props`.
- `src/*/**.csproj` (strip inline versions), `src/TourneyHub.Api/Program.cs` (real health checks).
- `.github/workflows/ci.yml` (add: `dotnet ef database update` step or migrate test; `dotnet list package --vulnerable`; `npm audit --audit-level=high`; secret scan e.g. gitleaks; keep OpenAPI lint).

## Guardrails (must hold)
No type suppression; secrets never committed/logged (NFR-021); warnings-as-errors preserved.

## Out of scope
Actual feature endpoints; SAST tuning beyond a basic scan.

## Definition of Done
AGENTS.md §8; CI is green and demonstrably *exercises* Postgres + migrations + scanning; `LICENSE` present; `spec/requirements.yaml` updated (NFR-013/015/016/019 → in_progress/done as appropriate).
