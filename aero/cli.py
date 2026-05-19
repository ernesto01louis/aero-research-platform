"""The `aero` command-line interface.

Stage 03 ships one command: `aero run naca0012`, which drives the OpenFOAM
walking skeleton end-to-end (prepare -> mesh -> solve -> load) and reports the
drag coefficient. Heavy dependencies (`xarray`, `mlflow`) are checked up front
so a missing extra fails fast with a friendly message rather than mid-solve.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import typer
from loguru import logger

from aero.adapters.openfoam import OpenFOAMSolver
from aero.adapters.openfoam.schemas import CaseSpec
from aero.orchestration import LocalSSHExecutor
from aero.provenance import log_skeleton_run

app = typer.Typer(name="aero", help="aero-research-platform CLI.", no_args_is_help=True)

_SOLVER_VERSION = "OpenFOAM-ESI v2412"
_REFERENCE_CASE = "naca0012"


@app.callback()
def _cli() -> None:
    """aero-research-platform command-line interface.

    A no-op callback so typer always treats `run` as a named subcommand
    (`aero run ...`) rather than collapsing it into the root command.
    """


def _repo_root() -> Path:
    """Repo root — the editable-installed package lives at ``<repo>/aero/``."""
    return Path(__file__).resolve().parents[1]


def _git_sha() -> str:
    """`git rev-parse HEAD` for the provenance tag, or 'unknown'."""
    try:
        out = subprocess.run(
            ["git", "-C", str(_repo_root()), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _sif_sha256(repo_root: Path) -> str:
    """The openfoam-esi.sif digest recorded in containers/SHA256SUMS."""
    sums = repo_root / "containers" / "SHA256SUMS"
    if sums.is_file():
        for line in sums.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == "openfoam-esi.sif":
                return parts[0]
    return "unknown"


def _detect_nfs_roots() -> tuple[Path, Path]:
    """(host root, in-LXC root) for the shared aero NFS dataset.

    On the Proxmox host the dataset is mounted at /mnt/aero-nfs and the LXC
    sees it at /mnt/aero; when the CLI runs on aero-build itself (the CI
    runner) both are /mnt/aero.
    """
    if os.path.ismount("/mnt/aero-nfs"):
        return Path("/mnt/aero-nfs"), Path("/mnt/aero")
    return Path("/mnt/aero"), Path("/mnt/aero")


def _naca0012_spec() -> CaseSpec:
    """The Stage 03 reference case: NACA 0012, Re=6e6, M=0.15, AoA 0deg."""
    return CaseSpec(name=_REFERENCE_CASE, reynolds=6.0e6, mach=0.15, aoa_deg=0.0)


@app.command()
def run(
    case: str = typer.Argument(..., help="Reference case name (Stage 03: 'naca0012')."),
    executor: str = typer.Option(
        "local-ssh", "--executor", help="Executor backend (Stage 03: 'local-ssh')."
    ),
    host: str = typer.Option("aero-build", "--host", help="LXC the solve runs on."),
) -> None:
    """Run a reference CFD case end-to-end and report its drag coefficient."""
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<level>{level: <7}</level> {message}")

    if case != _REFERENCE_CASE:
        typer.echo(f"unknown case '{case}' — Stage 03 ships only '{_REFERENCE_CASE}'", err=True)
        raise typer.Exit(code=2)
    if executor != "local-ssh":
        typer.echo(f"unknown executor '{executor}' — Stage 03 ships only 'local-ssh'", err=True)
        raise typer.Exit(code=2)
    for module in ("xarray", "mlflow"):
        if importlib.util.find_spec(module) is None:
            typer.echo(
                f"missing dependency '{module}' — install the extra:\n"
                "  pip install -e '.[openfoam]'",
                err=True,
            )
            raise typer.Exit(code=3)

    repo_root = _repo_root()
    host_root, remote_root = _detect_nfs_roots()
    spec = _naca0012_spec()
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

    mlflow_run = log_skeleton_run(
        case_name=spec.name,
        git_sha=_git_sha(),
        container_sif_sha256=_sif_sha256(repo_root),
        solver_version=_SOLVER_VERSION,
        cd=cd,
        cl=cl,
        iterations_to_convergence=iterations,
        final_residual=float(dataset.attrs["final_residual"]),
        mlruns_dir=repo_root / "mlruns",
    )

    typer.echo("")
    typer.echo(f"  case        {spec.name}  (Re={spec.reynolds:.2g}, AoA={spec.aoa_deg} deg)")
    typer.echo(f"  Cd          {cd:.6f}")
    typer.echo(f"  Cl          {cl:.6f}")
    typer.echo(f"  iterations  {iterations}")
    typer.echo(f"  MLflow run  {mlflow_run}")


if __name__ == "__main__":
    app()
