"""The `aero` command-line interface.

`aero run <case>` drives a reference CFD case end-to-end (prepare -> mesh ->
solve -> load) and logs the four-fold provenance tuple to the remote MLflow
server, mirrored into Postgres.

The case is composed by Hydra from `conf/` and validated, in exactly one
place, into the strict `CaseSpec` pydantic model — the Hydra->pydantic
boundary of `.claude/rules/fail-loud-pydantic.md`. Heavy dependencies are
checked up front so a missing extra fails fast with a friendly message.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import typer
from loguru import logger
from pydantic import ValidationError

from aero.adapters.openfoam import OpenFOAMSolver
from aero.adapters.openfoam.schemas import CaseSpec
from aero.orchestration import LocalSSHExecutor
from aero.provenance import ProvenanceError, compute_provenance

if TYPE_CHECKING:
    from omegaconf import DictConfig

app = typer.Typer(name="aero", help="aero-research-platform CLI.", no_args_is_help=True)

_SOLVER_VERSION = "OpenFOAM-ESI v2412"

# Runtime dependencies behind the openfoam + provenance extras. Checked up
# front so the CLI fails fast rather than mid-solve.
_REQUIRED_MODULES = ("xarray", "mlflow", "hydra", "omegaconf", "psycopg2", "boto3")


@app.callback()
def _cli() -> None:
    """aero-research-platform command-line interface.

    A no-op callback so typer always treats `run` as a named subcommand
    (`aero run ...`) rather than collapsing it into the root command.
    """


def _repo_root() -> Path:
    """Repo root — the editable-installed package lives at ``<repo>/aero/``."""
    return Path(__file__).resolve().parents[1]


def _detect_nfs_roots() -> tuple[Path, Path]:
    """(host root, in-LXC root) for the shared aero NFS dataset.

    On the Proxmox host the dataset is mounted at /mnt/aero-nfs and the LXC
    sees it at /mnt/aero; when the CLI runs on aero-build itself (the CI
    runner) both are /mnt/aero.
    """
    if os.path.ismount("/mnt/aero-nfs"):
        return Path("/mnt/aero-nfs"), Path("/mnt/aero")
    return Path("/mnt/aero"), Path("/mnt/aero")


def _compose_config(repo_root: Path, case: str) -> DictConfig:
    """Compose the layered Hydra config for `case` from `conf/`.

    Uses the Compose API (`initialize_config_dir` + `compose`), not
    `@hydra.main` — the latter hijacks `sys.argv` and the working directory,
    which collides with typer's own argument parsing. See ADR-004.
    """
    from hydra import compose, initialize_config_dir
    from hydra.core.global_hydra import GlobalHydra

    conf_dir = repo_root / "conf"
    GlobalHydra.instance().clear()
    with initialize_config_dir(version_base=None, config_dir=str(conf_dir)):
        return compose(config_name="config", overrides=[f"case={case}"])


def _format_validation_error(exc: ValidationError) -> str:
    """Render a pydantic ValidationError as friendly CLI output."""
    lines = ["invalid case config:"]
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "(root)"
        lines.append(f"  {loc}: {err['msg']}")
    return "\n".join(lines)


def _case_spec_from_cfg(cfg: DictConfig) -> CaseSpec:
    """The Hydra->pydantic boundary: resolve `cfg.case`, strict-validate it."""
    from omegaconf import OmegaConf

    plain = OmegaConf.to_container(cfg.case, resolve=True)
    try:
        return CaseSpec.model_validate(plain)
    except ValidationError as exc:
        typer.echo(_format_validation_error(exc), err=True)
        raise typer.Exit(code=2) from exc


@app.command()
def run(
    case: str = typer.Argument(..., help="Reference case name (Stage 04: 'naca0012')."),
    executor: str = typer.Option(
        "local-ssh", "--executor", help="Executor backend (Stage 04: 'local-ssh')."
    ),
    host: str = typer.Option("aero-build", "--host", help="LXC the solve runs on."),
    allow_dirty: bool = typer.Option(
        False,
        "--allow-dirty",
        help="Log an exploration run from a dirty tree (SHA tagged '-dirty').",
    ),
) -> None:
    """Run a reference CFD case end-to-end and report its drag coefficient."""
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<level>{level: <7}</level> {message}")

    if executor != "local-ssh":
        typer.echo(f"unknown executor '{executor}' — Stage 04 ships only 'local-ssh'", err=True)
        raise typer.Exit(code=2)
    for module in _REQUIRED_MODULES:
        if importlib.util.find_spec(module) is None:
            typer.echo(
                f"missing dependency '{module}' — install the extras:\n"
                "  pip install -e '.[openfoam,provenance]'",
                err=True,
            )
            raise typer.Exit(code=3)

    repo_root = _repo_root()
    if not (repo_root / "conf" / "case" / f"{case}.yaml").is_file():
        typer.echo(f"unknown case '{case}' — no conf/case/{case}.yaml", err=True)
        raise typer.Exit(code=2)

    # --- compose + validate the case (Hydra -> pydantic boundary) -------------
    cfg = _compose_config(repo_root, case)
    spec = _case_spec_from_cfg(cfg)

    # --- four-fold provenance, computed BEFORE the solve so a dirty tree or a
    #     missing component fails fast (and before any MLflow run exists) ------
    from omegaconf import OmegaConf

    from aero.provenance.db import resolve_dsn
    from aero.provenance.mlflow import log_artifact, log_metrics, start_provenance_run

    resolved = cast(dict[str, Any], OmegaConf.to_container(cfg, resolve=True))
    try:
        db_dsn = resolve_dsn()
        provenance = compute_provenance(
            repo_root=repo_root,
            container_sif=str(cfg.provenance.container_sif),
            resolved_config=resolved,
            allow_dirty=allow_dirty,
        )
    except ProvenanceError as exc:
        typer.echo(f"provenance error: {exc}", err=True)
        raise typer.Exit(code=4) from exc
    logger.info(f"provenance git_sha={provenance.git_sha}")

    # --- solve ---------------------------------------------------------------
    host_root, remote_root = _detect_nfs_roots()
    solver = OpenFOAMSolver(host_nfs_root=host_root, remote_nfs_root=remote_root)
    ssh = LocalSSHExecutor(host=host, ssh_user="root", repo_root=repo_root)

    case_dir = solver.prepare(spec)
    typer.echo(f"prepared case {case_dir.run_id} at {case_dir.host_path}")

    mesh = solver.mesh(case_dir, ssh)
    if not mesh.ok:
        typer.echo("blockMesh failed — case did not mesh", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"meshed ({mesh.n_cells} cells); running simpleFoam on {host} ...")

    result = solver.run(case_dir, ssh)
    if result.returncode != 0:
        typer.echo(f"simpleFoam failed (rc={result.returncode})", err=True)
        raise typer.Exit(code=1)

    dataset = solver.load(result)
    cd = float(dataset.attrs["cd"])
    cl = float(dataset.attrs["cl"])
    iterations = int(dataset.attrs["iterations_to_convergence"])
    final_residual = float(dataset.attrs["final_residual"])

    # --- log: four-fold tuple as MLflow tags + the Postgres mirror -----------
    with start_provenance_run(
        tracking_uri=str(cfg.mlflow.tracking_uri),
        experiment=str(cfg.mlflow.experiment),
        provenance=provenance,
        case_name=spec.name,
        db_dsn=db_dsn,
        extra_tags={"solver_version": _SOLVER_VERSION},
    ) as mlflow_run:
        log_metrics(
            {
                "cd": cd,
                "cl": cl,
                "iterations_to_convergence": float(iterations),
                "final_residual": final_residual,
            }
        )
        log_artifact(result.post_processing_host_path)
        run_id = str(mlflow_run.info.run_id)

    typer.echo("")
    typer.echo(f"  case        {spec.name}  (Re={spec.reynolds:.2g}, AoA={spec.aoa_deg} deg)")
    typer.echo(f"  Cd          {cd:.6f}")
    typer.echo(f"  Cl          {cl:.6f}")
    typer.echo(f"  iterations  {iterations}")
    typer.echo(f"  config_hash {provenance.config_hash}")
    typer.echo(f"  MLflow run  {run_id}")


if __name__ == "__main__":
    app()
