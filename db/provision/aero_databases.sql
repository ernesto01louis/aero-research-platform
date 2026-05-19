-- Stage 04 — aero provenance databases on the SHARED Postgres LXC 202.
--
-- ADDITIVE ONLY. This script creates two new aero-owned databases and two
-- new roles. It must NEVER touch a pre-existing non-aero database, role, or
-- extension (Hard Rule 11 / Stage 04 guardrails 7-8). Run it as a Postgres
-- superuser AFTER the operator has reviewed it and replied `approved`.
--
-- Run:
--   psql -h 192.168.2.184 -U <superuser> -d postgres \
--        -v pw_mlflow="'<from Vault: aero/postgres/aero_mlflow_user>'" \
--        -v pw_reader="'<from Vault: aero/postgres/aero_provenance_reader>'" \
--        -f db/provision/aero_databases.sql
--
-- Passwords are passed as psql variables so they never appear in this file
-- or in shell history written to disk (Hard Rule 7).

\set ON_ERROR_STOP on

-- aero_mlflow_user — owns both aero databases; the only read/write identity.
CREATE ROLE aero_mlflow_user LOGIN PASSWORD :pw_mlflow;

-- aero_provenance_reader — read-only on aero_provenance, for cross-run queries.
CREATE ROLE aero_provenance_reader LOGIN PASSWORD :pw_reader;

-- MLflow's own tracking metadata (experiments, runs, tags, metrics).
CREATE DATABASE aero_mlflow OWNER aero_mlflow_user;

-- The four-fold provenance mirror (table created later by alembic).
CREATE DATABASE aero_provenance OWNER aero_mlflow_user;

-- pgvector — required cluster-wide for later stages (literature mining,
-- Stage 15). Enabled inside aero_provenance only; created IF NOT EXISTS so a
-- pre-existing cluster install is left untouched.
\connect aero_provenance
CREATE EXTENSION IF NOT EXISTS vector;

GRANT CONNECT ON DATABASE aero_provenance TO aero_provenance_reader;
GRANT USAGE ON SCHEMA public TO aero_provenance_reader;

-- alembic creates mlflow_artifact_provenance as aero_mlflow_user, so the
-- default-privilege grant must target that role. This makes the reader's
-- SELECT automatic for every table aero_mlflow_user creates from here on.
ALTER DEFAULT PRIVILEGES FOR ROLE aero_mlflow_user IN SCHEMA public
    GRANT SELECT ON TABLES TO aero_provenance_reader;

-- For tables that already exist (none at provision time); harmless to re-run
-- AFTER `alembic upgrade head` to cover mlflow_artifact_provenance directly.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO aero_provenance_reader;
