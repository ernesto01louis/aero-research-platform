"""Minimal MLflow run logger for the Stage 03 walking skeleton.

Logs the two provenance-contract tags available at this stage (`git_sha`,
`container_sif_sha256`) plus the case metrics to a *local* `mlruns/` store.

# TODO(stage-04): supersede this with the full four-fold provenance logger —
# add `dvc_input_hash` and `config_hash` (they need DVC-tracked inputs and
# Hydra, which arrive in Stage 04), and point the tracking URI at the
# aero-mlflow server plus the Postgres provenance mirror. See ADR-003.
"""

from __future__ import annotations

from pathlib import Path

EXPERIMENT = "stage-03-walking-skeleton"


def log_skeleton_run(
    *,
    case_name: str,
    git_sha: str,
    container_sif_sha256: str,
    solver_version: str,
    cd: float,
    cl: float,
    iterations_to_convergence: int,
    final_residual: float,
    mlruns_dir: Path | str,
) -> str:
    """Log one walking-skeleton run to a local MLflow store; return its run id.

    `mlflow` is imported lazily — this keeps `import aero.provenance` free of
    the `aero[openfoam]` extra (PLATFORM-NOT-HUB).
    """
    import mlflow

    tracking_uri = f"file://{Path(mlruns_dir).expanduser().resolve()}"
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run() as run:
        mlflow.set_tags(
            {
                "git_sha": git_sha,
                "container_sif_sha256": container_sif_sha256,
                "case_name": case_name,
                "solver_version": solver_version,
                "stage": "03",
            }
        )
        mlflow.log_metrics(
            {
                "cd": cd,
                "cl": cl,
                "iterations_to_convergence": float(iterations_to_convergence),
                "final_residual": final_residual,
            }
        )
        return str(run.info.run_id)
