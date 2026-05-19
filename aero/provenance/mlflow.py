"""Four-fold provenance MLflow logger.

Supersedes the Stage 03 interim `mlflow_basic.py`. Every run now logs the full
four-fold tuple — `git_sha`, `dvc_input_hash`, `container_sif_sha256`,
`config_hash` — as MLflow tags against the *remote* tracking server on the
`aero-mlflow` LXC, and mirrors the tuple into the Postgres `aero_provenance` DB.

`mlflow` is imported lazily inside every function. Python 3 absolute imports
mean `import mlflow` here resolves to the installed PyPI package, not this
sibling module — but there is deliberately no top-level `import mlflow`, so
`import aero.provenance` stays free of the `aero[provenance]` extra
(PLATFORM-NOT-HUB).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from aero.provenance.four_fold import ProvenanceError, ProvenanceTuple

# Default remote experiment for stage-04+ runs. Override via Hydra config.
EXPERIMENT = "aero-provenance"


@contextmanager
def start_provenance_run(
    *,
    tracking_uri: str,
    experiment: str,
    provenance: ProvenanceTuple,
    case_name: str,
    db_dsn: str,
    extra_tags: Mapping[str, str] | None = None,
) -> Iterator[Any]:
    """Open an MLflow run with the four-fold tuple tagged and mirrored.

    The active `mlflow.ActiveRun` is yielded. `provenance` is an already-built
    `ProvenanceTuple`, so the four tags are guaranteed complete — compute it
    via `compute_provenance` *before* entering this context manager, so a
    provenance failure aborts before any run exists.

    On entry the four tags (plus `case_name`, `stage`, and any `extra_tags`)
    are set, then the tuple is mirrored into Postgres in one transaction. A
    mirror failure raises and aborts the run — the four-fold contract is not
    satisfied without the mirror row.
    """
    import mlflow

    from aero.provenance.db import mirror_provenance_row

    tags = dict(provenance.as_mlflow_tags())
    tags["case_name"] = case_name
    tags["stage"] = "04"
    if extra_tags:
        tags.update(extra_tags)

    missing = [
        k
        for k in ("git_sha", "dvc_input_hash", "container_sif_sha256", "config_hash")
        if not tags.get(k)
    ]
    if missing:  # defensive — ProvenanceTuple validation should make this unreachable
        raise ProvenanceError(f"provenance tuple incomplete: missing {missing}")

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run() as run:
        mlflow.set_tags(tags)
        mirror_provenance_row(run_id=str(run.info.run_id), provenance=provenance, db_dsn=db_dsn)
        yield run


def log_metrics(metrics: Mapping[str, float]) -> None:
    """Log run metrics to the active MLflow run (call inside `start_provenance_run`)."""
    import mlflow

    mlflow.log_metrics(dict(metrics))


def log_artifact(path: Path | str) -> None:
    """Log a file or directory artifact to the active run's MinIO artifact store."""
    import mlflow

    target = Path(path)
    if not target.exists():
        raise ProvenanceError(f"artifact not found: {target}")
    if target.is_dir():
        mlflow.log_artifacts(str(target))
    else:
        mlflow.log_artifact(str(target))
