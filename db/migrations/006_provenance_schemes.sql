-- Stage 23 - per-term provenance semantics in the mirror (ADR-052, ADR-053)
--
-- From Stage 23 every run's tuple names the semantics of its two non-trivial terms:
-- `dvc_input_hash_scheme` (repo-sync-state/v0 | declared-dvc-pointers-md5/v1) and
-- `container_sif_sha256_scheme` (sha256sums-lookup/v0 | sif-sha256-verified-at-launch/v1), plus
-- `dvc_inputs`, the canonical JSON of the declared inputs whose content addresses the DVC term
-- digests. The mirror carries them byte-identical to the MLflow tags of the same names.
--
-- STRICTLY ADDITIVE, and NO BACKFILL. The columns are nullable and have no default, so every
-- historical row stays exactly as it was: NULL in all three means "recorded before Stage 23"
-- (the ADR-004 sync-state digest and the SHA256SUMS lookup), and nothing ever relabels a row.
-- The CHECK keeps the two scheme columns both-or-neither, and sets `dvc_inputs` exactly when the
-- DVC term is the declared-pointer scheme (the v0 sync-state digest uses no declaration), so a
-- half-labelled row, or a v0 row that reads as "declared no inputs", cannot be written.
--
-- Authoritative DDL: applied by the alembic revision 006_provenance_schemes.py, which executes
-- this file verbatim. Edit here, not in the .py. The operator applies it from the Proxmox host
-- (`alembic upgrade head`, the 005 precedent) BEFORE the first PR that writes these columns is
-- pushed, because pull-request CI writes to the shared mirror. The old six-column writer keeps
-- working against the migrated table, because the new columns are nullable.

ALTER TABLE mlflow_artifact_provenance
    ADD COLUMN IF NOT EXISTS dvc_input_hash_scheme TEXT,
    ADD COLUMN IF NOT EXISTS container_sif_sha256_scheme TEXT,
    ADD COLUMN IF NOT EXISTS dvc_inputs TEXT;

ALTER TABLE mlflow_artifact_provenance
    ADD CONSTRAINT provenance_schemes_consistent CHECK (
        (dvc_input_hash_scheme IS NULL) = (container_sif_sha256_scheme IS NULL)
        AND (dvc_inputs IS NOT NULL)
            = (dvc_input_hash_scheme IS NOT DISTINCT FROM 'declared-dvc-pointers-md5/v1')
    );
