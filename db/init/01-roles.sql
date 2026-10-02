-- TourneyHub — database roles (DATA-MODEL.md §11.1, ADR-006).
--
-- Runs once, on first container start, as POSTGRES_USER (the superuser that also
-- owns the database and is used by Alembic as `tourneyhub_migrator`).
--
-- Why this file exists: Row-Level Security is NEVER applied to a superuser, and
-- `FORCE ROW LEVEL SECURITY` only covers the table OWNER. If the API connected as
-- POSTGRES_USER, layer 3 of ADR-006 would be silently inert and the REVOKE on the
-- audit tables meaningless. `CREATE ROLE` is cluster-level and not idempotent per
-- database, so it cannot live in an Alembic revision.
--
-- Self-host equivalent: `uv run tourneyhub bootstrap`.

\set app_pw   `echo "${TOURNEYHUB_APP_DB_PASSWORD:-tourneyhub_app}"`
\set admin_pw `echo "${TOURNEYHUB_ADMIN_DB_PASSWORD:-tourneyhub_admin}"`

-- The API connects as this role: no superuser, no BYPASSRLS, does not inherit the
-- schema owner (NOINHERIT), so FORCE RLS fully applies to it.
CREATE ROLE tourneyhub_app LOGIN PASSWORD :'app_pw' NOINHERIT;

-- AdminSession, outbox relay, retention job, platform-admin listings. Every use is audited.
CREATE ROLE tourneyhub_admin LOGIN PASSWORD :'admin_pw' NOINHERIT BYPASSRLS;

GRANT USAGE ON SCHEMA public TO tourneyhub_app, tourneyhub_admin;

-- Default privileges so future migrations do not have to remember the grants.
--
-- Deliberately only SELECT, INSERT for the app role. UPDATE and DELETE are granted
-- per table in the migration that creates it. The reason is partitioning: privileges
-- do NOT propagate down a partition tree, so a blanket default grant hands full DML
-- on every new audit partition to the app role and a REVOKE on the parent does not
-- take it back (DATA-MODEL.md §4.3). Append-only therefore rests on a trigger, and
-- the default grant is narrowed so the ACL tells the truth as well.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT ON TABLES TO tourneyhub_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tourneyhub_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO tourneyhub_app, tourneyhub_admin;

-- Per-table exceptions (append-only audit, PII-bearing queues, credentials) are
-- GRANTed/REVOKEd in the migration that creates each table — see DATA-MODEL.md §11.1.
