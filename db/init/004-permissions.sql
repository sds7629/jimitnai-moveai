-- platform-infra: least-privilege DB role for the backend application.
--
-- Why a second role: the init scripts run as POSTGRES_USER, which owns
-- every table and therefore always bypasses GRANT/REVOKE (table owners
-- cannot be locked out of their own tables). To make the append-only
-- constraint on operational_snapshots / simulation_results / approvals /
-- audit_log actually unbreakable (not just an app-code convention), the
-- backend must connect as a *different*, non-owner role that we can
-- restrict with GRANT.
--
-- `moveai_app` is that role. backend/.env's DATABASE_URL must point at
-- this role (see .env.example), not at POSTGRES_USER.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'moveai_app') THEN
    CREATE ROLE moveai_app LOGIN PASSWORD 'moveai_app';
  END IF;
END
$$;

DO $$
DECLARE
  dbname text := current_database();
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO moveai_app', dbname);
END
$$;

GRANT USAGE ON SCHEMA public TO moveai_app;

-- Append-only tables: SELECT + INSERT only. UPDATE/DELETE intentionally
-- never granted (REVOKE is redundant with a plain GRANT statement, but is
-- issued explicitly so the intent is unmistakable to anyone reading this
-- file, and so re-running it after a future accidental grant fixes things).
GRANT SELECT, INSERT ON audit_log, operational_snapshots, simulation_results, approvals TO moveai_app;
REVOKE UPDATE, DELETE ON audit_log, operational_snapshots, simulation_results, approvals FROM moveai_app;

-- Mutable tables: legitimate in-place field updates happen here
-- (incident status transitions, candidate validation_status, document
-- validity windows, decision package regeneration, DAG node/edge upkeep,
-- seed scenario bookkeeping).
GRANT SELECT, INSERT, UPDATE ON
    incidents,
    response_candidates,
    decision_packages,
    impact_dag_nodes,
    impact_dag_edges,
    documents,
    document_chunks,
    seed_scenarios
TO moveai_app;

-- Sequences backing the BIGSERIAL primary keys above need USAGE for INSERT
-- to work at all.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO moveai_app;
