-- Stage 20 - multi-container provenance (ADR-038)
--
-- A partitioned FSI coupling runs OpenFOAM out of `precice-fsi.sif` and CalculiX
-- out of `calculix-precice.sif`, so one `container_sif_sha256` cannot describe
-- what ran. `container_sif_set` carries the full roster.
--
-- STRICTLY ADDITIVE. The column is nullable and the four existing columns are
-- untouched, so every historical row stays valid and the Stage-04 completeness
-- check (which SELECTs the four) keeps passing unchanged. NULL means
-- single-container -- which is every run before Stage 20 -- and is deliberately
-- distinct from an empty string, so "no roster" and "an empty roster" cannot be
-- confused in a query.
--
-- The value is byte-identical to the `container_sif_set` MLflow tag:
--     name=<sha256>,name=<sha256>   (name-sorted, comma-separated)
-- Keeping the mirror byte-comparable with the tag is what lets the completeness
-- check compare them directly instead of parsing either side.
--
-- Authoritative DDL: applied by the alembic revision 005_container_set.py, which
-- executes this file verbatim. Edit here, not in the .py.

ALTER TABLE mlflow_artifact_provenance
    ADD COLUMN IF NOT EXISTS container_sif_set TEXT;

-- Partial index: only multi-container runs are worth indexing here, and the
-- predicate keeps the index off every single-container row.
CREATE INDEX IF NOT EXISTS idx_provenance_container_set
    ON mlflow_artifact_provenance (container_sif_set)
    WHERE container_sif_set IS NOT NULL;
