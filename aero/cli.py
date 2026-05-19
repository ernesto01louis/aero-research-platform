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


# =============================================================================
# `aero vv` — the V&V harness against NASA TMR reference cases (Stage 05)
# =============================================================================
vv_app = typer.Typer(
    name="vv",
    help="V&V harness — run NASA TMR verification cases and report their status.",
    no_args_is_help=True,
)
app.add_typer(vv_app, name="vv")

# Extra modules the `vv run` / `vv report` paths need on top of `_REQUIRED_MODULES`.
_VV_MODULES = ("scipy",)


def _vv_settings(repo_root: Path) -> tuple[str, str, str]:
    """`(tracking_uri, experiment, container_sif)` for V&V runs, from `conf/`.

    The V&V cases are Python-defined (`aero.vv.tmr.TMR_CASES`), so only the
    non-case Hydra layers are needed; composing the default config yields them.
    """
    cfg = _compose_config(repo_root, "naca0012")
    return (
        str(cfg.mlflow.tracking_uri),
        str(cfg.mlflow.experiment),
        str(cfg.provenance.container_sif),
    )


@vv_app.command("list")
def vv_list() -> None:
    """List the registered V&V benchmark cases."""
    from aero.vv.tmr import TMR_CASES

    typer.echo("V&V benchmark cases (NASA TMR):\n")
    for name, case in TMR_CASES.items():
        typer.echo(f"  {name}")
        typer.echo(f"      {case.description}")
        metrics = ", ".join(f"{m.name} ({m.tolerance:.0%})" for m in case.metrics())
        typer.echo(f"      metrics: {metrics}\n")


@vv_app.command("run")
def vv_run(
    case: str = typer.Option(..., "--case", help="TMR case name (see `aero vv list`)."),
    executor: str = typer.Option("local-ssh", "--executor", help="Executor backend."),
    host: str = typer.Option("aero-build", "--host", help="LXC the solve runs on."),
    allow_dirty: bool = typer.Option(
        False, "--allow-dirty", help="Allow a dirty tree (SHA tagged '-dirty')."
    ),
    mesh_sweep: bool = typer.Option(
        False, "--mesh-sweep", help="Run a 3-grid GCI study instead of a single solve."
    ),
) -> None:
    """Run one NASA TMR verification case and report its V&V status."""
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<level>{level: <7}</level> {message}")

    if executor != "local-ssh":
        typer.echo(f"unknown executor '{executor}' — only 'local-ssh' is supported", err=True)
        raise typer.Exit(code=2)
    for module in (*_REQUIRED_MODULES, *_VV_MODULES):
        if importlib.util.find_spec(module) is None:
            typer.echo(
                f"missing dependency '{module}' — install the extras:\n"
                "  pip install -e '.[openfoam,provenance,vv]'",
                err=True,
            )
            raise typer.Exit(code=3)

    from aero.vv import BenchmarkError, BenchmarkRunner, MeshSweep
    from aero.vv.tmr import TMR_CASES

    if case not in TMR_CASES:
        known = ", ".join(TMR_CASES)
        typer.echo(f"unknown V&V case '{case}' — known cases: {known}", err=True)
        raise typer.Exit(code=2)

    repo_root = _repo_root()
    benchmark = TMR_CASES[case]
    spec = benchmark.case_spec()

    from aero.provenance.db import resolve_dsn

    tracking_uri, experiment, container_sif = _vv_settings(repo_root)
    try:
        db_dsn = resolve_dsn()
        provenance = compute_provenance(
            repo_root=repo_root,
            container_sif=container_sif,
            # The case spec IS the V&V run's config — hash it for config_hash.
            resolved_config=spec.model_dump(mode="json"),
            allow_dirty=allow_dirty,
        )
    except ProvenanceError as exc:
        typer.echo(f"provenance error: {exc}", err=True)
        raise typer.Exit(code=4) from exc

    host_root, remote_root = _detect_nfs_roots()
    solver = OpenFOAMSolver(host_nfs_root=host_root, remote_nfs_root=remote_root)
    ssh = LocalSSHExecutor(host=host, ssh_user="root", repo_root=repo_root)
    runner = BenchmarkRunner(
        solver=solver,
        executor=ssh,
        tracking_uri=tracking_uri,
        experiment=experiment,
        db_dsn=db_dsn,
        solver_version=_SOLVER_VERSION,
        stage="05",
    )

    try:
        if mesh_sweep:
            report = MeshSweep(benchmark, metric=benchmark.sweep_metric).run(
                runner, provenance=provenance, repo_root=repo_root
            )
            typer.echo("")
            typer.echo(f"  GCI mesh sweep — {report.case_name}  (metric: {report.metric})")
            for g in report.grids:
                typer.echo(
                    f"    ratio {g.refinement_ratio:>4}  "
                    f"{g.n_cells:>8} cells  {report.metric} = {g.metric_value:.6g}"
                )
            typer.echo(f"  observed order p     {report.observed_order_p:.3f}")
            typer.echo(f"  extrapolated value   {report.extrapolated_value:.6g}")
            typer.echo(f"  GCI (fine grid)      {report.gci_fine_pct:.3f} %")
            typer.echo(f"  monotonic            {report.monotonic}")
            if not report.monotonic:
                typer.echo("  WARNING: non-monotone convergence — GCI is not strictly valid")
            return

        result = runner.run(benchmark, provenance=provenance, repo_root=repo_root)
    except BenchmarkError as exc:
        typer.echo(f"benchmark error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("")
    typer.echo(f"  case        {result.case_name}")
    typer.echo(f"  status      {result.status.upper()}")
    for m in result.metrics:
        mark = "ok " if m.passed else "OVER"
        typer.echo(f"  {m.name:<10}  {mark}  error {m.error:.4%}  (tolerance {m.tolerance:.1%})")
    typer.echo(f"  MLflow run  {result.mlflow_run_id}")
    if result.status != "pass":
        raise typer.Exit(code=1)


@vv_app.command("report")
def vv_report(
    latest: bool = typer.Option(False, "--latest", help="Show only the most recent run per case."),
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    html_path: str = typer.Option("", "--html", help="Also write the HTML dashboard here."),
) -> None:
    """Report recent V&V runs from MLflow — the production-gate green/red check."""
    import json as _json

    if importlib.util.find_spec("mlflow") is None:
        typer.echo("missing dependency 'mlflow' — install '.[provenance]'", err=True)
        raise typer.Exit(code=3)

    from mlflow.tracking import MlflowClient

    from aero.vv import DashboardEntry, render_dashboard

    tracking_uri, experiment, _ = _vv_settings(_repo_root())
    client = MlflowClient(tracking_uri=tracking_uri)
    exp = client.get_experiment_by_name(experiment)
    if exp is None:
        typer.echo(f"no MLflow experiment '{experiment}'", err=True)
        raise typer.Exit(code=1)

    runs = client.search_runs([exp.experiment_id], order_by=["start_time DESC"], max_results=500)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run in runs:
        tag = run.data.tags.get("validation_tag")
        if not tag or tag.endswith("-sweep"):
            continue
        if latest and tag in seen:
            continue
        seen.add(tag)
        errors = {k[:-6]: float(v) for k, v in run.data.metrics.items() if k.endswith("_error")}
        rows.append(
            {
                "case": tag,
                "status": run.data.tags.get("vv_status", "unknown"),
                "run_id": run.info.run_id,
                "git_sha": run.data.tags.get("git_sha", ""),
                "metric_errors": errors,
            }
        )

    if html_path:
        render_dashboard(
            [
                DashboardEntry(
                    case_name=r["case"],
                    status=r["status"],
                    git_sha=r["git_sha"],
                    mlflow_run_id=r["run_id"],
                    metric_errors=r["metric_errors"],
                )
                for r in rows
            ],
            Path(html_path),
        )
        typer.echo(f"dashboard written to {html_path}")

    if json_out:
        typer.echo(_json.dumps(rows, indent=2))
        return
    if not rows:
        typer.echo("no V&V runs found in MLflow")
        return
    typer.echo("\n  V&V runs" + (" (latest per case)" if latest else "") + ":\n")
    for r in rows:
        mark = "GREEN" if r["status"] == "pass" else "RED  "
        typer.echo(f"  [{mark}] {r['case']:<24} {r['status']:<8} {r['run_id']}")


if __name__ == "__main__":
    app()
