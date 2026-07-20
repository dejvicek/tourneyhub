# Step 01 — Tenancy as a real boundary

- **Scope:** MVP
- **Status:** ✅ done
- **Depends on:** 00
- **Unblocks:** 05, 06, and every tenant-scoped feature
- **Requirements:** NFR-004, NFR-024, FR-151, FR-152, FR-154, BR-012, BR-015

## Goal
Turn tenant isolation from a DbContext unit-demo into an enforced, end-to-end security boundary: the active organization is resolved server-side on every request, writes fail closed when no tenant is resolved, and cross-tenant access is impossible across the API — proven by a Postgres-backed multi-org test through a real endpoint.

## Context & why
Today `ITenantContext`/`AddDbContext` are only a comment in `Program.cs`; nothing resolves the org from a request; the SaveChanges guard stamps `Guid.Empty` instead of failing closed; there is no FK on `organization_id`; and isolation is only tested at the DbContext level on SQLite. This is the #1 claims-vs-reality gap.

## Design notes (decisions & gotchas)
- **Resolve org server-side only** (NFR-004, FR-154): from the authenticated principal's membership + an explicit active-org selector (claim or `X-Organization-Id` validated against membership) — **never trust a raw client id**. Implement `ITenantContext` as a scoped service populated by middleware AFTER auth.
- **Fail closed:** a write/read requiring a tenant with `HasTenant == false` MUST throw/deny (403/400), never default to `Guid.Empty`. Update `StampAndGuardTenant` to reject unresolved tenant.
- **Immutability + integrity:** `organization_id` is immutable after insert (guard on `OriginalValue`), add a real **FK** `leagues.organization_id → organizations.id`, keep the composite index.
- **EF query filters are not a complete boundary.** Document and lint against bypass paths: `IgnoreQueryFilters`, raw SQL without scope, `ExecuteUpdate/ExecuteDelete`, tracked-entity reuse across tenants. Provide a scoped-repository/base-query pattern others must use.
- **Register DI:** `AddDbContext<TourneyHubDbContext>(UseNpgsql(cfg.GetConnectionString("Postgres")))` + `AddScoped<ITenantContext, HttpTenantContext>()`.

## API contract
No new endpoints; add the org-scoping behavior to all tenant-scoped routes. Document `X-Organization-Id` (or the active-org claim) in `api/openapi.yaml` security section.

## Data model / migration
Migration: add FK `leagues.organization_id → organizations.id` (ON DELETE RESTRICT), enforce `organization_id` NOT NULL (already), keep `(organization_id, id)` index. Make `OrganizationId` immutable in EF config.

## Acceptance criteria (Given/When/Then)
- Given a user who is a member of Org A only, When they request Org B's data via any endpoint, Then 404/403 — never data.
- Given a request with no resolvable org, When it performs a tenant-scoped write, Then it is rejected (fail closed) and nothing is persisted.
- Given an entity loaded in Org A, When code attempts to persist it under Org B, Then SaveChanges throws (existing guard, now on original value).
- Given a league row, When its org is deleted, Then the FK prevents orphaning.

## Tests to write
- **Postgres-backed** (Testcontainers) integration test hitting a real endpoint via `WebApplicationFactory` with two orgs and two users; asserts no cross-org read/write.
- Extend `TenantIsolationTests`: "no tenant resolved → fail closed"; "organization_id immutable".
- Keep/upgrade the SQLite tests; add the Postgres variant to CI (Step 00).

## Files to create / modify
- `src/TourneyHub.Api/Program.cs` (DI + tenant middleware), `src/TourneyHub.Api/Middleware/TenantResolutionMiddleware.cs`, `src/TourneyHub.Infrastructure/Tenancy/HttpTenantContext.cs`.
- `src/TourneyHub.Infrastructure/Persistence/TourneyHubDbContext.cs` (fail-closed guard, immutability), new migration.
- `tests/TourneyHub.Integration.Tests/*` (Postgres endpoint test).

## Guardrails (must hold)
NFR-004/024 (this step IS the guardrail); module boundaries; no client-supplied tenant trust.

## Out of scope
Auth itself (Step 05 provides the principal; here, stub/test auth is acceptable behind a test handler); org creation UI (Step 06).

## Definition of Done
AGENTS.md §8; Postgres-backed cross-org test green in CI; fail-closed + FK verified; `requirements.yaml` FR-151/152/154, NFR-004/024 → in_progress/done.
