"""Postgres mirror of the four-fold provenance tuple.

Every MLflow run's four-tuple is mirrored into the `mlflow_artifact_provenance`
table in the `aero_provenance` database on the shared Postgres LXC 202. The
table is a *mirror* — MLflow remains the source of truth — but it makes
cross-run provenance queries ("every run against container SHA X") fast.

`psycopg2` is imported lazily so `import aero.provenance` stays free of the
`aero[provenance]` extra (PLATFORM-NOT-HUB). The connection string is sourced
from the environment, never from a config file — it carries a password
(Hard Rule 7). See ADR-004.
"""

from __future__ import annotations

import os

from aero.provenance.four_fold import ProvenanceError, ProvenanceTuple

#: Env var holding the libpq DSN for the `aero_provenance` DB. On `aero-mlflow`
#: it is rendered from Vault into `/etc/aero/mlflow.env` (mode 0600).
DSN_ENV_VAR = "AERO_PROVENANCE_DSN"

_INSERT_SQL = (
    "INSERT INTO mlflow_artifact_provenance "
    "(run_id, git_sha, dvc_input_hash, container_sif_sha256, config_hash) "
    "VALUES (%s, %s, %s, %s, %s)"
)


def resolve_dsn() -> str:
    """Return the `aero_provenance` DSN from the environment, or fail loud."""
    dsn = os.environ.get(DSN_ENV_VAR)
    if not dsn:
        raise ProvenanceError(
            f"{DSN_ENV_VAR} is not set — the Postgres provenance mirror needs a "
            "connection string. On aero-mlflow it is rendered from Vault into "
            "/etc/aero/mlflow.env; for a local run, export it. See ADR-004."
        )
    return dsn


def mirror_provenance_row(*, run_id: str, provenance: ProvenanceTuple, db_dsn: str) -> None:
    """Insert the four-tuple for `run_id` into `mlflow_artifact_provenance`.

    The insert runs in one transaction: `with conn` commits on success and
    rolls back on any exception. A failure raises `ProvenanceError` — the
    four-fold contract is not satisfied if the mirror row is missing.
    """
    import psycopg2

    try:
        conn = psycopg2.connect(db_dsn)
    except psycopg2.Error as exc:
        raise ProvenanceError(f"cannot connect to {DSN_ENV_VAR}: {exc}") from exc
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                _INSERT_SQL,
                (
                    run_id,
                    provenance.git_sha,
                    provenance.dvc_input_hash,
                    provenance.container_sif_sha256,
                    provenance.config_hash,
                ),
            )
    except psycopg2.Error as exc:
        raise ProvenanceError(f"failed to mirror provenance row for run {run_id}: {exc}") from exc
    finally:
        conn.close()
