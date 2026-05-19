-- Stage 04 — Provenance Backbone
--
-- The `mlflow_artifact_provenance` table mirrors the four-fold provenance
-- tuple of every MLflow run into the `aero_provenance` database, indexed for
-- fast cross-run queries. MLflow remains the source of truth; this table is a
-- mirror (Stage 04 guardrail 5). See ADR-004.
--
-- Authoritative DDL: applied by the alembic revision 004_provenance.py, which
-- executes this file verbatim. Edit here, not in the .py.

CREATE TABLE mlflow_artifact_provenance (
    run_id               TEXT PRIMARY KEY,
    git_sha              TEXT NOT NULL,
    dvc_input_hash       TEXT NOT NULL,
    container_sif_sha256 TEXT NOT NULL,
    config_hash          TEXT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_provenance_git ON mlflow_artifact_provenance (git_sha);
CREATE INDEX idx_provenance_dvc ON mlflow_artifact_provenance (dvc_input_hash);
