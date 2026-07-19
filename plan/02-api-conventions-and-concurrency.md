# Step 02 — API conventions & optimistic concurrency

- **Scope:** MVP
- **Status:** ⬜ not started
- **Depends on:** 01
- **Unblocks:** 05–19 (every write endpoint)
- **Requirements:** NFR-023, NFR-002, NFR-014, §17 (API), FR-045 (idempotency support)

## Goal
Establish the cross-cutting API contract once — RFC 7807 errors with a stable code catalog, pagination, idempotency, rate limiting, correlation IDs — and make optimistic concurrency **real** (DB concurrency token → ETag → `If-Match` → 409) so all later write endpoints inherit it.

## Context & why
`Entity.Version` and ETag docs exist but nothing enforces them; there is no 409 path, no error catalog, no pagination/idempotency middleware. Building these per-endpoint later causes drift. Do it once here.

## Design notes (decisions & gotchas)
- **Concurrency:** map `Entity.Version` as an EF **concurrency token** (`IsConcurrencyToken()`), increment it on each update; expose it as a **weak ETag**; require `If-Match` on mutating endpoints of versioned resources; return **409 Problem** on `DbUpdateConcurrencyException`. (NFR-023, per `03-adr-core-semantics.md`.)
- **Errors:** RFC 7807 `application/problem+json` via a global exception handler; a **stable error-code catalog** (enum/string constants) — every thrown domain error maps to a code. Publish the catalog in `api/openapi.yaml` and a short `spec/error-catalog.md`.
- **Idempotency:** `Idempotency-Key` header on create endpoints (registrations/payments/payouts); store key→response for a retention window; replay returns the original response (FR-045 support).
- **Pagination:** cursor-based for append-heavy lists; allow-listed `sort`/`filter`; reject unknown params (§17).
- **Observability:** correlation-id middleware (accept/generate `X-Correlation-Id`), structured logging scope with `organizationId` + correlation id (NFR-014). No PII/secrets in logs (NFR-021).
- **Rate limiting:** ASP.NET rate limiter; stricter buckets on auth/finance; per-IP + per-user/tenant.

## API contract
Add reusable components to `api/openapi.yaml`: `Problem` (already), `ETag`/`If-Match` (already) — wire them onto mutating operations; document `Idempotency-Key`, pagination params, and the error-code list. This step **hardens** the contract; it adds no resources.

## Data model / migration
Concurrency token config only (no schema change if `Version` column exists). Idempotency store table `idempotency_keys(org_id, key, request_hash, response, created_at)`.

## Acceptance criteria (Given/When/Then)
- Given two concurrent updates to the same versioned entity, When the second commits with a stale `If-Match`, Then it gets **409** and no data loss.
- Given a mutating request without `If-Match` on a versioned resource, Then **428 Precondition Required** (or documented 400).
- Given any handled error, Then the response is `application/problem+json` with a stable `code`.
- Given a create with a repeated `Idempotency-Key`, Then the original response is replayed (no duplicate).
- Given any request, Then logs carry a correlation id + org id and no secrets.

## Tests to write
- Integration (Postgres): concurrency conflict → 409; idempotent replay; problem+json shape; rate-limit 429.
- Unit: error→code mapping table is exhaustive.

## Files to create / modify
- `src/TourneyHub.Api/` — `ProblemDetails` handler, `Middleware/CorrelationIdMiddleware.cs`, rate-limiter config, idempotency filter.
- `src/TourneyHub.Application/Common/ErrorCodes.cs`, `spec/error-catalog.md`.
- `src/TourneyHub.Infrastructure/Persistence/` — concurrency token config, idempotency store, migration.
- `api/openapi.yaml` (harden), `tests/TourneyHub.Integration.Tests/*`.

## Guardrails (must hold)
Concurrency (NFR-023) is now enforced; tenancy (idempotency store is tenant-scoped); no PII in logs; no type suppression.

## Out of scope
Feature endpoints; distributed rate limiting store (single-node limiter is fine for MVP).

## Definition of Done
AGENTS.md §8; 409/idempotency/problem+json tests green; error catalog published; `requirements.yaml` NFR-023/002/014 → in_progress/done.
