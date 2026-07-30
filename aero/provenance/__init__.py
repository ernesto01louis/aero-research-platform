"""Run provenance — the four-fold reproducibility contract.

Every CFD or training run logs the tuple (`git_sha`, `dvc_input_hash`,
`container_sif_sha256`, `config_hash`) to MLflow and mirrors it into Postgres.
Only stdlib + pydantic names are imported eagerly; the MLflow / psycopg2
machinery is lazy-imported inside `mlflow.py` and `db.py` (PLATFORM-NOT-HUB).
"""

from __future__ import annotations

from aero.provenance.four_fold import (
    ContainerRef,
    ProvenanceError,
    ProvenanceTuple,
    compute_provenance,
    container_roster,
)

__all__ = [
    "ContainerRef",
    "ProvenanceError",
    "ProvenanceTuple",
    "compute_provenance",
    "container_roster",
]
