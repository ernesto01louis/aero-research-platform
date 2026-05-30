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

from aero.adapters._base import Solver
from aero.adapters.jax_fluids import JaxFluidsSolver
from aero.adapters.nekrs import NekRSSolver
from aero.adapters.openfoam import OpenFOAMSolver
from aero.adapters.openfoam.schemas import CaseSpec
from aero.adapters.pyfr import PyFRSolver
from aero.adapters.su2 import SU2Solver
from aero.orchestration import LocalSSHExecutor
from aero.orchestration._base import Executor
from aero.provenance import ProvenanceError, compute_provenance

if TYPE_CHECKING:
    from omegaconf import DictConfig

app = typer.Typer(name="aero", help="aero-research-platform CLI.", no_args_is_help=True)

# One platform version-string per solver, logged as the MLflow `solver_version`
# tag (Invariant 3) — the concrete SIF SHA256 also enters the four-fold tuple.
_SOLVER_VERSIONS: dict[str, str] = {
    "openfoam": "OpenFOAM-ESI v2412",
    "su2": "SU2 v8",
    "pyfr": "PyFR 1.15.0",
    "nekrs": "NekRS v23.0",
    "jax-fluids": "JAX-Fluids v0.2.1",
}

# Per-solver SIF basenames — looked up in containers/SHA256SUMS during
# compute_provenance to populate the four-fold tuple's container_sif_sha256.
_SOLVER_SIF: dict[str, str] = {
    "openfoam": "openfoam-esi.sif",
    "su2": "su2-v8.sif",
    "pyfr": "pyfr.sif",
    "nekrs": "nekrs.sif",
    "jax-fluids": "jax-fluids.sif",
}

# Per-solver runtime imports, checked up front so the CLI fails fast rather
# than mid-solve. `provenance` extras (mlflow/hydra/omegaconf/psycopg2/boto3)
# are common to every path; the openfoam path keeps xarray for downstream
# field post-processing; pyfr/nekrs host-side need only h5py + numpy + the
# provenance core (the solver binaries live inside the SIFs).
_PROVENANCE_MODULES = ("mlflow", "hydra", "omegaconf", "psycopg2", "boto3")
_REQUIRED_MODULES_BY_SOLVER: dict[str, tuple[str, ...]] = {
    "openfoam": ("xarray", *_PROVENANCE_MODULES),
    "su2": _PROVENANCE_MODULES,
    "pyfr": ("h5py", "mako", *_PROVENANCE_MODULES),
    "nekrs": _PROVENANCE_MODULES,
    # Stage 08 — host-side only needs h5py to load JAX-Fluids HDF5 outputs in
    # the adapter's load() step. jax / jaxlib / jaxfluids run inside the SIF
    # (or in-process on aero-dev for differentiable_run); not required for
    # the standard `aero run` CLI path.
    "jax-fluids": ("h5py", *_PROVENANCE_MODULES),
}

# Per-solver `aero[<extras>]` hint shown when a required module is missing.
_SOLVER_EXTRAS_HINT: dict[str, str] = {
    "openfoam": "openfoam,provenance",
    "su2": "su2,provenance",
    "pyfr": "pyfr,provenance",
    "nekrs": "nekrs,provenance",
    "jax-fluids": "jax-fluids,provenance",
}


def _build_solver(name: str, *, host_root: Path, remote_root: Path, repo_root: Path) -> Solver:
    """Construct the named solver adapter — openfoam/su2/pyfr/nekrs/jax-fluids."""
    if name == "openfoam":
        return OpenFOAMSolver(host_nfs_root=host_root, remote_nfs_root=remote_root)
    if name == "su2":
        return SU2Solver(host_nfs_root=host_root, remote_nfs_root=remote_root, repo_root=repo_root)
    if name == "pyfr":
        return PyFRSolver(host_nfs_root=host_root, remote_nfs_root=remote_root, repo_root=repo_root)
    if name == "nekrs":
        return NekRSSolver(
            host_nfs_root=host_root, remote_nfs_root=remote_root, repo_root=repo_root
        )
    if name == "jax-fluids":
        return JaxFluidsSolver(
            host_nfs_root=host_root, remote_nfs_root=remote_root, repo_root=repo_root
        )
    raise typer.BadParameter(
        f"unknown solver {name!r} — choose one of 'openfoam', 'su2', 'pyfr', 'nekrs', 'jax-fluids'"
    )


def _build_executor(
    name: str,
    *,
    host: str,
    repo_root: Path,
    pod_type: str,
    container_image: str | None,
    projected_hours: float,
) -> Executor:
    """Construct the named executor — `local-ssh` or `runpod`.

    `runpod` requires `RUNPOD_API_KEY` in the environment (Vault-rendered;
    see operator-followups §3 of Stage-07). The cost-cap ledger path
    defaults to `/etc/aero/runpod-ledger.json` (CONSTITUTION Invariant 8).
    """
    if name == "local-ssh":
        return LocalSSHExecutor(host=host, ssh_user="root", repo_root=repo_root)
    if name == "runpod":
        api_key = os.environ.get("RUNPOD_API_KEY")
        if not api_key:
            raise typer.BadParameter(
                "RUNPOD_API_KEY env var not set — provision it via Vault "
                "(operator-followups §3) before launching a paid GPU run."
            )
        if container_image is None:
            raise typer.BadParameter(
                "--container-image is required for --executor runpod "
                "(e.g. ghcr.io/ernesto01louis/aero-pyfr:v1.15.0)."
            )
        from aero.orchestration.cost_cap import CostCap
        from aero.orchestration.runpod import RunPodExecutor

        return RunPodExecutor(
            api_key=api_key,
            pod_type=pod_type,
            container_image=container_image,
            cost_cap=CostCap(),
            repo_root=repo_root,
            projected_hours=projected_hours,
        )
    raise typer.BadParameter(f"unknown executor {name!r} — choose 'local-ssh' or 'runpod'")


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
    case: str = typer.Argument(..., help="Reference case name (e.g. 'naca0012')."),
    executor: str = typer.Option(
        "local-ssh", "--executor", help="Executor backend — 'local-ssh' or 'runpod' (Stage 07)."
    ),
    solver_name: str = typer.Option(
        "openfoam",
        "--solver",
        help="Solver adapter — 'openfoam', 'su2', 'pyfr', 'nekrs' (Stage 07), or "
        "'jax-fluids' (Stage 08).",
    ),
    host: str = typer.Option(
        "aero-build", "--host", help="LXC the solve runs on (local-ssh only)."
    ),
    pod_type: str = typer.Option(
        "NVIDIA H100 PCIe",
        "--pod-type",
        help="RunPod pod-type (runpod executor only) — see POD_TYPE_HOURLY_USD.",
    ),
    container_image: str | None = typer.Option(
        None,
        "--container-image",
        help="OCI image (GHCR tag) for the RunPod pod (runpod executor only).",
    ),
    projected_hours: float = typer.Option(
        0.5,
        "--projected-hours",
        help="Projected pod uptime in hours; used for the cost-cap check.",
    ),
    allow_dirty: bool = typer.Option(
        False,
        "--allow-dirty",
        help="Log an exploration run from a dirty tree (SHA tagged '-dirty').",
    ),
) -> None:
    """Run a reference CFD case end-to-end and report its drag coefficient."""
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<level>{level: <7}</level> {message}")

    if executor not in {"local-ssh", "runpod"}:
        typer.echo(
            f"unknown executor '{executor}' — choose 'local-ssh' or 'runpod' (Stage 07)",
            err=True,
        )
        raise typer.Exit(code=2)
    if solver_name not in _REQUIRED_MODULES_BY_SOLVER:
        known = ", ".join(_REQUIRED_MODULES_BY_SOLVER)
        typer.echo(f"unknown solver '{solver_name}' — choose one of: {known}", err=True)
        raise typer.Exit(code=2)
    extras_hint = _SOLVER_EXTRAS_HINT[solver_name]
    for module in _REQUIRED_MODULES_BY_SOLVER[solver_name]:
        if importlib.util.find_spec(module) is None:
            typer.echo(
                f"missing dependency '{module}' — install the extras:\n"
                f"  pip install -e '.[{extras_hint}]'",
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
    solver = _build_solver(
        solver_name, host_root=host_root, remote_root=remote_root, repo_root=repo_root
    )
    ssh = _build_executor(
        executor,
        host=host,
        repo_root=repo_root,
        pod_type=pod_type,
        container_image=container_image,
        projected_hours=projected_hours,
    )

    case_dir = solver.prepare(spec)
    typer.echo(f"prepared case {case_dir.run_id} at {case_dir.host_path}")

    mesh = solver.mesh(case_dir, ssh)
    if not mesh.ok:
        typer.echo(f"{solver_name} meshing failed — case did not mesh", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"meshed ({mesh.n_elements} elements); running {solver_name} on {host} ...")

    result = solver.run(case_dir, ssh)
    if result.returncode != 0:
        typer.echo(f"{solver_name} solver failed (rc={result.returncode})", err=True)
        raise typer.Exit(code=1)

    solve = solver.load(result)
    iterations = solve.iterations_to_convergence
    final_residual = solve.final_residual

    # --- log: four-fold tuple as MLflow tags + the Postgres mirror -----------
    metrics: dict[str, float] = {
        "iterations_to_convergence": float(iterations),
        "final_residual": final_residual,
    }
    if solve.cd is not None:
        metrics["cd"] = solve.cd
    if solve.cl is not None:
        metrics["cl"] = solve.cl
    metrics.update(solve.scalars)
    with start_provenance_run(
        tracking_uri=str(cfg.mlflow.tracking_uri),
        experiment=str(cfg.mlflow.experiment),
        provenance=provenance,
        case_name=spec.name,
        db_dsn=db_dsn,
        extra_tags={"solver_version": _SOLVER_VERSIONS[solver_name]},
    ) as mlflow_run:
        log_metrics(metrics)
        log_artifact(result.output_host_path)
        run_id = str(mlflow_run.info.run_id)

    typer.echo("")
    re_str = (
        f"  case        {spec.name}  (Re={spec.reynolds:.2g}, AoA={spec.aoa_deg} deg)"
        if hasattr(spec, "reynolds") and hasattr(spec, "aoa_deg")
        else f"  case        {spec.name}"
    )
    typer.echo(re_str)
    if solve.cd is not None:
        typer.echo(f"  Cd          {solve.cd:.6f}")
    if solve.cl is not None:
        typer.echo(f"  Cl          {solve.cl:.6f}")
    for k, v in solve.scalars.items():
        typer.echo(f"  {k:<11} {v:.6g}")
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
    """List the registered V&V benchmark cases (TMR + transonic + scale-resolving)."""
    from aero.vv.scale_resolving import SCALE_RESOLVING_CASES
    from aero.vv.tmr import TMR_CASES
    from aero.vv.transonic import TRANSONIC_CASES

    for header, cases in (
        ("V&V benchmark cases (NASA TMR):", TMR_CASES),
        ("V&V benchmark cases (transonic — Stage 06):", TRANSONIC_CASES),
        ("V&V benchmark cases (scale-resolving — Stage 07):", SCALE_RESOLVING_CASES),
    ):
        typer.echo(header + "\n")
        for name, case in cases.items():
            typer.echo(f"  {name}")
            typer.echo(f"      {case.description}")
            metrics = ", ".join(f"{m.name} ({m.tolerance:.0%})" for m in case.metrics())
            typer.echo(f"      metrics: {metrics}\n")


@vv_app.command("run")
def vv_run(
    case: str = typer.Option(..., "--case", help="V&V case name (see `aero vv list`)."),
    executor: str = typer.Option(
        "local-ssh",
        "--executor",
        help="Executor backend — 'local-ssh' or 'runpod' (Stage 07).",
    ),
    solver_name: str = typer.Option(
        "openfoam",
        "--solver",
        help="Solver adapter — 'openfoam', 'su2', 'pyfr', or 'nekrs' (Stage 07).",
    ),
    host: str = typer.Option(
        "aero-build", "--host", help="LXC the solve runs on (local-ssh only)."
    ),
    pod_type: str = typer.Option(
        "NVIDIA H100 PCIe",
        "--pod-type",
        help="RunPod pod-type (runpod executor only).",
    ),
    container_image: str | None = typer.Option(
        None,
        "--container-image",
        help="OCI image for the RunPod pod (runpod executor only).",
    ),
    projected_hours: float = typer.Option(
        0.5, "--projected-hours", help="Projected pod uptime in hours; gates the cost cap."
    ),
    allow_dirty: bool = typer.Option(
        False, "--allow-dirty", help="Allow a dirty tree (SHA tagged '-dirty')."
    ),
    mesh_sweep: bool = typer.Option(
        False, "--mesh-sweep", help="Run a 3-grid GCI study instead of a single solve."
    ),
) -> None:
    """Run one V&V case (TMR / transonic / scale-resolving) and report its status."""
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<level>{level: <7}</level> {message}")

    if executor not in {"local-ssh", "runpod"}:
        typer.echo(f"unknown executor '{executor}' — choose 'local-ssh' or 'runpod'", err=True)
        raise typer.Exit(code=2)
    if solver_name not in _REQUIRED_MODULES_BY_SOLVER:
        known = ", ".join(_REQUIRED_MODULES_BY_SOLVER)
        typer.echo(f"unknown solver '{solver_name}' — choose one of: {known}", err=True)
        raise typer.Exit(code=2)
    extras_hint = f"{_SOLVER_EXTRAS_HINT[solver_name]},vv"
    for module in (*_REQUIRED_MODULES_BY_SOLVER[solver_name], *_VV_MODULES):
        if importlib.util.find_spec(module) is None:
            typer.echo(
                f"missing dependency '{module}' — install the extras:\n"
                f"  pip install -e '.[{extras_hint}]'",
                err=True,
            )
            raise typer.Exit(code=3)

    from aero.vv import BenchmarkError, BenchmarkRunner, MeshSweep
    from aero.vv.scale_resolving import SCALE_RESOLVING_CASES
    from aero.vv.tmr import TMR_CASES
    from aero.vv.transonic import TRANSONIC_CASES

    all_cases = {**TMR_CASES, **TRANSONIC_CASES, **SCALE_RESOLVING_CASES}
    if case not in all_cases:
        known = ", ".join(all_cases)
        typer.echo(f"unknown V&V case '{case}' — known cases: {known}", err=True)
        raise typer.Exit(code=2)

    repo_root = _repo_root()
    benchmark = all_cases[case]
    spec = benchmark.case_spec()

    from aero.provenance.db import resolve_dsn

    tracking_uri, experiment, default_sif = _vv_settings(repo_root)
    # The Hydra config's `container_sif` points at the OpenFOAM SIF; per-solver
    # selection overrides that with the SIF the solver actually runs in. The
    # config_hash is the case spec (mesh-agnostic), so cross-solver runs share
    # a config_hash, distinguished only by `solver_version` and the SIF SHA.
    container_sif = _SOLVER_SIF.get(solver_name, Path(default_sif).name)
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
    solver = _build_solver(
        solver_name, host_root=host_root, remote_root=remote_root, repo_root=repo_root
    )
    ssh = _build_executor(
        executor,
        host=host,
        repo_root=repo_root,
        pod_type=pod_type,
        container_image=container_image,
        projected_hours=projected_hours,
    )
    # Stage is informational on the MLflow side; each adapter is tagged with
    # the stage that introduced it.
    if solver_name == "jax-fluids":
        stage_str = "08"
    elif solver_name in {"pyfr", "nekrs"}:
        stage_str = "07"
    else:
        stage_str = "06"
    runner = BenchmarkRunner(
        solver=solver,
        executor=ssh,
        tracking_uri=tracking_uri,
        experiment=experiment,
        db_dsn=db_dsn,
        solver_version=_SOLVER_VERSIONS[solver_name],
        stage=stage_str,
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


# =============================================================================
# `aero cost` — cost-cap ledger inspection (Stage 07)
# =============================================================================
cost_app = typer.Typer(
    name="cost",
    help="RunPod cost-cap ledger inspection — see CONSTITUTION Invariant 8.",
    no_args_is_help=True,
)
app.add_typer(cost_app, name="cost")


@cost_app.command("show")
def cost_show(
    n: int = typer.Option(10, "--last", help="Show the last N ledger entries (default 10)."),
) -> None:
    """Show the current cost-cap ledger — MTD spend, cap, recent entries.

    Reads `/etc/aero/runpod-ledger.json` (or whatever `CostCap.ledger_path`
    points at). Useful as a pre-launch dry-run before `aero run --executor
    runpod` and as the post-mortem after a paid GPU session.
    """
    from aero.orchestration.cost_cap import CostCap

    cap = CostCap()
    ledger = cap.ensure_ledger()
    mtd = ledger.month_to_date_usd()
    typer.echo("")
    typer.echo(f"  cap                ${cap.cap_usd:.2f}")
    typer.echo(f"  month-to-date      ${mtd:.2f}")
    typer.echo(f"  remaining          ${cap.cap_usd - mtd:.2f}")
    typer.echo(f"  ledger entries     {len(ledger.entries)}")
    if ledger.has_orphaned():
        typer.echo("  WARNING: orphaned entries present — launches will be REFUSED")
    typer.echo("")
    if not ledger.entries:
        typer.echo("  (no entries)")
        return
    typer.echo(f"  last {min(n, len(ledger.entries))} entries:")
    for e in ledger.entries[-n:]:
        tag = e.tag.upper()
        billed = e.billed_cost_usd
        actual = f"{e.actual_hours:.3f}h" if e.actual_hours is not None else "running"
        typer.echo(f"    [{tag:<8}] {e.run_id:<32} {e.pod_type:<24} {actual:<12} ${billed:.2f}")


@cost_app.command("clear-orphan")
def cost_clear_orphan(
    run_id: str = typer.Argument(..., help="run_id of the orphan entry to retag."),
    new_tag: str = typer.Option(
        "errored",
        "--tag",
        help="Replacement tag: 'ok' or 'errored' (cannot be 'running' or 'orphaned').",
    ),
) -> None:
    """Manually re-tag an orphaned ledger entry so further launches are permitted.

    Use after verifying out-of-band (via the RunPod console) that the pod
    is actually terminated. CONSTITUTION Invariant 8 — operator action,
    not automatic.
    """
    if new_tag not in {"ok", "errored"}:
        typer.echo(f"--tag must be 'ok' or 'errored', got {new_tag!r}", err=True)
        raise typer.Exit(code=2)
    from aero.orchestration.cost_cap import CostCap

    cap = CostCap()
    ledger = cap.ensure_ledger()
    for i, e in enumerate(ledger.entries):
        if e.run_id == run_id and e.tag == "orphaned":
            ledger.entries[i] = e.model_copy(update={"tag": new_tag})
            cap._write_ledger(ledger)
            typer.echo(f"cleared orphan {run_id!r} -> tag={new_tag}")
            return
    typer.echo(f"no orphaned entry with run_id={run_id!r}", err=True)
    raise typer.Exit(code=1)


# =============================================================================
# `aero surrogate` — train surrogate baselines, log the eight provenance tags,
# attach the CertificateOfValidity as a JSON artifact (Stage 08, ADR-008)
# =============================================================================
surrogate_app = typer.Typer(
    name="surrogate",
    help="Train surrogate baselines (MLP / FNO / MGN); enforce CertificateOfValidity.",
    no_args_is_help=True,
)
app.add_typer(surrogate_app, name="surrogate")


@surrogate_app.command("train")
def surrogate_train(
    baseline: str = typer.Option(
        ...,
        "--baseline",
        help="Baseline name: 'mlp_baseline' | 'fno_smoke' | 'mgn_smoke'.",
    ),
    config_path: str = typer.Option(
        None,
        "--config",
        help="Hydra-style YAML config. Default: conf/surrogate/baselines/<baseline>.yaml.",
    ),
    executor: str = typer.Option(
        "local-ssh",
        "--executor",
        help="'local-ssh' (in-process on aero-dev) or 'runpod' (Stage 09 follow-up).",
    ),
    pod_type: str = typer.Option(
        "NVIDIA H100 PCIe",
        "--pod-type",
        help="RunPod pod-type (runpod executor only).",
    ),
    container_image: str | None = typer.Option(
        None,
        "--container-image",
        help="OCI image for the RunPod pod (runpod executor only).",
    ),
    projected_hours: float = typer.Option(
        0.1,
        "--projected-hours",
        help="Pre-launch cost estimate (cost-cap gate; runpod only).",
    ),
    allow_dirty: bool = typer.Option(
        False,
        "--allow-dirty",
        help="Log a `-dirty` SHA instead of refusing — exploration runs only.",
    ),
) -> None:
    """Train a surrogate baseline and log the eight Stage-08 provenance tags.

    The flow (Stage 08, ADR-008):

    1. Resolve the four-fold provenance tuple
       (``ProvenanceTuple(git_sha, dvc_input_hash, container_sif_sha256,
       config_hash)``); refuses to start if any component cannot be
       computed.
    2. Load the dataset via the discriminated loader (CC-BY-SA path or
       CC-BY-NC quarantined path).
    3. Construct the baseline + applicability envelope from the resolved
       config.
    4. ``fit()`` — runs in-process for ``local-ssh`` (Stage 08 default; the
       three smoke baselines all complete in seconds-to-minutes on CPU).
       The ``runpod`` path is plumbed but defers to Stage 09's production
       training entrypoint for the on-pod training script.
    5. ``set_certificate()`` — builds the cert, propagating the
       ``non_commercial`` taint flag.
    6. ``SurrogateProvenanceTags.from_certificate(...)`` composes the
       four-fold tuple + four surrogate tags; ``log_to_mlflow(...)``
       writes all eight to the active run.
    7. The cert JSON lands as the MLflow artifact
       ``certificates/<baseline>.json``.
    """
    import json
    from datetime import UTC, datetime

    if baseline not in {"mlp_baseline", "fno_smoke", "mgn_smoke"}:
        typer.echo(
            f"unknown baseline {baseline!r} — choose 'mlp_baseline', 'fno_smoke', or 'mgn_smoke'",
            err=True,
        )
        raise typer.Exit(code=2)
    if executor not in {"local-ssh", "runpod"}:
        typer.echo(f"unknown executor {executor!r}", err=True)
        raise typer.Exit(code=2)
    if executor == "runpod":
        typer.echo(
            "the runpod surrogate-training executor is a Stage 09 follow-up "
            "(needs an on-pod training script + GHCR mirror of surrogate-smoke.sif); "
            "use --executor local-ssh for the Stage-08 smoke validation.",
            err=True,
        )
        raise typer.Exit(code=2)

    # Validate the host-side modules the smoke training needs are present.
    for module in ("torch", "mlflow"):
        if importlib.util.find_spec(module) is None:
            typer.echo(
                f"module {module!r} is not installed — install "
                "`aero[surrogate-smoke,provenance]` before running this command.",
                err=True,
            )
            raise typer.Exit(code=2)

    repo_root = Path.cwd()

    cfg_path = (
        Path(config_path)
        if config_path
        else repo_root / "conf" / "surrogate" / "baselines" / f"{baseline}.yaml"
    )
    if not cfg_path.is_file():
        typer.echo(f"config not found: {cfg_path}", err=True)
        raise typer.Exit(code=2)

    from omegaconf import OmegaConf

    cfg = OmegaConf.load(cfg_path)
    resolved = OmegaConf.to_container(cfg, resolve=True)
    assert isinstance(resolved, dict)
    assert isinstance(resolved.get("dataset"), dict)
    assert isinstance(resolved.get("train"), dict)
    assert isinstance(resolved.get("envelope"), dict)

    # --- four-fold provenance up front ----------------------------------------
    from aero.provenance.four_fold import (
        compute_provenance,
    )
    from aero.surrogates._common._dataset_pick import build_loader  # local helper below
    from aero.surrogates._common.certificate import ApplicabilityEnvelope
    from aero.surrogates._common.loaders import dataset_hash
    from aero.surrogates._common.provenance import SurrogateProvenanceTags, hparam_hash

    container_sif_basename = "surrogate-smoke.sif"
    # `resolved` is the OmegaConf -> plain dict result and is always keyed on
    # str; the cast is purely to give mypy strict the precise Mapping[str, Any]
    # the four-fold provenance contract requires.
    resolved_str_keys = cast(dict[str, Any], resolved)
    try:
        provenance = compute_provenance(
            repo_root=repo_root,
            container_sif=container_sif_basename,
            resolved_config=resolved_str_keys,
            allow_dirty=allow_dirty,
        )
    except Exception as exc:
        typer.echo(f"provenance computation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    # --- dataset --------------------------------------------------------------
    loader = build_loader(
        dataset_id=resolved["dataset"]["id"],
        repo_root=repo_root,
        acknowledge_noncommercial=bool(resolved["dataset"].get("acknowledge_noncommercial", False)),
    )
    train_dvc_hash = dataset_hash(repo_root, loader.dvc_path)

    # --- baseline construction ------------------------------------------------
    envelope = ApplicabilityEnvelope(
        re_range=tuple(resolved["envelope"]["re_range"]),
        mach_range=tuple(resolved["envelope"]["mach_range"]),
        aoa_range_deg=tuple(resolved["envelope"]["aoa_range_deg"]),
        geometry_class=str(resolved["envelope"]["geometry_class"]),
    )
    from aero.surrogates._common.base import Surrogate
    from aero.surrogates.baselines import FNOSmoke, MGNSmoke, MLPBaseline

    # Explicit if/elif dispatch (not a class-table dict) because the latter
    # makes mypy strict treat the value type as `type[Surrogate]`, which is
    # abstract and rejects the concrete subclasses' kwargs.
    surrogate: Surrogate
    if baseline == "mlp_baseline":
        surrogate = MLPBaseline(
            training_dataset_dvc_hash=train_dvc_hash,
            dataset_id=loader.dataset_id,
            applicability_envelope=envelope,
        )
    elif baseline == "fno_smoke":
        surrogate = FNOSmoke(
            training_dataset_dvc_hash=train_dvc_hash,
            dataset_id=loader.dataset_id,
            applicability_envelope=envelope,
        )
    elif baseline == "mgn_smoke":
        surrogate = MGNSmoke(
            training_dataset_dvc_hash=train_dvc_hash,
            dataset_id=loader.dataset_id,
            applicability_envelope=envelope,
        )
    else:  # pragma: no cover — guarded by the up-front baseline-validity check
        raise typer.BadParameter(f"unknown baseline {baseline!r}")

    typer.echo(f"training {baseline} on {loader.dataset_id} ({len(loader)} samples) ...")
    surrogate.fit(iter(loader), **resolved["train"])
    cert = surrogate.set_certificate()
    typer.echo(f"  cert_status={cert.cert_status} non_commercial={cert.non_commercial}")

    # --- MLflow run + eight tags + cert artifact ------------------------------
    import mlflow

    mlflow.set_experiment("aero-surrogates")
    with mlflow.start_run(run_name=f"{baseline}-{loader.dataset_id}") as run:
        tags = SurrogateProvenanceTags.from_certificate(
            provenance=provenance,
            cert=cert,
            hparam_hash=hparam_hash(resolved["train"]),
        )
        for k, v in tags.as_mlflow_tags().items():
            mlflow.set_tag(k, v)
        # Cert JSON as an artifact under certificates/
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(cert.model_dump(mode="json"), f, indent=2, default=str)
            cert_tmp = Path(f.name)
        mlflow.log_artifact(str(cert_tmp), artifact_path="certificates")
        cert_tmp.unlink(missing_ok=True)
        typer.echo(f"  logged 8 tags + certificate JSON to MLflow run {run.info.run_id}")
        typer.echo(
            f"  fingerprint: git={provenance.git_sha[:12]} "
            f"dvc-inputs={provenance.dvc_input_hash[:12]} "
            f"cfg={provenance.config_hash[:12]} "
            f"train-data={train_dvc_hash[:12]} (issued {datetime.now(UTC).isoformat()})"
        )


if __name__ == "__main__":
    app()
