"""`OpenFOAMSolver` — the Stage 03 walking-skeleton CFD adapter.

The pipeline is `prepare -> mesh -> run -> load`:

* `prepare` writes an OpenFOAM case onto the shared NFS dataset (a filesystem
  operation on the aero process's host);
* `mesh` and `run` execute `blockMesh` / `simpleFoam` inside the OpenFOAM SIF
  on a remote LXC, through an `Executor`;
* `load` parses the force-coefficient output into an `xarray.Dataset`.

This adapter is deliberately OpenFOAM-only and concrete — there is no
`Solver` base class. The multi-solver abstraction is Stage 06's job, when SU2
provides the second data point that reveals the right shape (ADR-003).
"""

from __future__ import annotations

import re
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

from aero.adapters.openfoam.case_writer import write_case
from aero.adapters.openfoam.schemas import (
    CASE_BIND_TARGET,
    DEFAULT_HOST_NFS_ROOT,
    DEFAULT_REMOTE_NFS_ROOT,
    DEFAULT_SIF_PATH,
    RUNS_SUBDIR,
    CaseDir,
    CaseSpec,
    MeshHandle,
    ResultHandle,
)
from aero.orchestration._base import Executor

if TYPE_CHECKING:
    import xarray as xr

_CELL_COUNT_RE = re.compile(r"nCells:\s*(\d+)")
_P_RESIDUAL_RE = re.compile(r"Solving for p,\s*Initial residual\s*=\s*([0-9.eE+-]+)")


def build_apptainer_exec(
    *,
    sif_path: str,
    case_bind_source: str,
    openfoam_command: str,
    case_bind_target: str = CASE_BIND_TARGET,
) -> str:
    """Compose the `apptainer exec` command line that runs one OpenFOAM command.

    The case directory is bind-mounted to `case_bind_target` inside the SIF;
    the command runs there via a *login* shell (`bash -lc`) because the
    upstream image activates OpenFOAM through `/etc/profile.d` (see
    `containers/openfoam-esi.def`). Pure and deterministic — this is the seam
    the adapter unit test pins.
    """
    inner = f"cd {shlex.quote(case_bind_target)} && {openfoam_command}"
    return (
        f"apptainer exec --bind "
        f"{shlex.quote(case_bind_source)}:{shlex.quote(case_bind_target)} "
        f"{shlex.quote(sif_path)} bash -lc {shlex.quote(inner)}"
    )


class OpenFOAMSolver:
    """Runs the NACA-class walking-skeleton case through OpenFOAM-ESI."""

    def __init__(
        self,
        *,
        sif_path: str = DEFAULT_SIF_PATH,
        host_nfs_root: Path = DEFAULT_HOST_NFS_ROOT,
        remote_nfs_root: Path = DEFAULT_REMOTE_NFS_ROOT,
    ) -> None:
        self.sif_path = sif_path
        self.host_nfs_root = Path(host_nfs_root)
        self.remote_nfs_root = Path(remote_nfs_root)

    def prepare(self, case: CaseSpec) -> CaseDir:
        """Write the OpenFOAM case onto the shared NFS dataset."""
        run_id = f"{case.name}-{datetime.now(UTC):%Y%m%d-%H%M%S}"
        host_path = self.host_nfs_root / RUNS_SUBDIR / run_id
        remote_path = self.remote_nfs_root / RUNS_SUBDIR / run_id
        logger.info("preparing case {} at {}", run_id, host_path)
        write_case(case, host_path)
        return CaseDir(run_id=run_id, spec=case, host_path=host_path, remote_path=remote_path)

    def mesh(self, case_dir: CaseDir, executor: Executor) -> MeshHandle:
        """Run `blockMesh` inside the SIF, then confirm a polyMesh was written.

        `mesh` takes the `Executor` as an argument (like `run`); the Stage 03
        prompt's `mesh(case_dir)` signature omitted it, but meshing executes
        inside the SIF on a remote host exactly as the solve does — the
        symmetry is recorded in ADR-003.
        """
        command = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=str(case_dir.remote_path),
            openfoam_command="blockMesh",
        )
        result = executor.run(command, timeout_s=900)
        polymesh = case_dir.host_path / "constant" / "polyMesh" / "points"
        ok = result.ok and polymesh.is_file()
        if not ok:
            logger.error("blockMesh failed (rc={}):\n{}", result.returncode, result.stdout)
        cells = _CELL_COUNT_RE.search(result.stdout)
        return MeshHandle(
            case_dir=case_dir,
            ok=ok,
            n_cells=int(cells.group(1)) if cells else None,
        )

    def run(self, case_dir: CaseDir, executor: Executor) -> ResultHandle:
        """Run `simpleFoam` inside the SIF (long-running, via the executor)."""
        command = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=str(case_dir.remote_path),
            openfoam_command="simpleFoam",
        )
        result = executor.run(command, long_running=True, session=f"sf-{case_dir.run_id}")
        if not result.ok:
            logger.error("simpleFoam failed (rc={})", result.returncode)
        return ResultHandle(
            case_dir=case_dir,
            returncode=result.returncode,
            post_processing_host_path=case_dir.host_path / "postProcessing",
            solver_log=result.stdout,
        )

    def load(self, result: ResultHandle) -> xr.Dataset:
        """Parse the `forceCoeffs` output into a typed `xarray.Dataset`.

        The `forceCoeffs` function object writes a columnar `coefficient.dat`
        (not a field file), so this parses with `numpy.loadtxt` — Ofpp is for
        mesh/field files and is unused here (ADR-003). `xarray` is imported
        lazily so importing this module does not require `aero[openfoam]`.
        """
        import xarray as xr

        coeff_file = _coefficient_file(result.post_processing_host_path)
        columns, data = _read_coefficient_dat(coeff_file)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        iteration = data[:, columns.index("Time")].astype(int)
        cd = data[:, columns.index("Cd")]
        cl = data[:, columns.index("Cl")]
        return xr.Dataset(
            {"cd": ("iteration", cd), "cl": ("iteration", cl)},
            coords={"iteration": iteration},
            attrs={
                "run_id": result.case_dir.run_id,
                "case_name": result.case_dir.spec.name,
                "cd": float(cd[-1]),
                "cl": float(cl[-1]),
                "iterations_to_convergence": int(iteration[-1]),
                "final_residual": _final_residual(result.solver_log),
                "source": str(coeff_file),
            },
        )


def _coefficient_file(post_processing: Path) -> Path:
    """Locate the forceCoeffs `coefficient.dat` under a postProcessing tree."""
    for name in ("coefficient.dat", "forceCoeffs.dat"):
        hits = sorted(post_processing.glob(f"forceCoeffs1/*/{name}"))
        if hits:
            return hits[0]
    raise FileNotFoundError(
        f"no forceCoeffs coefficient file under {post_processing} — "
        "did simpleFoam run and write postProcessing/?"
    )


def _read_coefficient_dat(path: Path) -> tuple[list[str], np.ndarray]:
    """Return (column names, data array) from an OpenFOAM coefficient file."""
    header: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            header = stripped.lstrip("#").split()  # last comment line wins
        elif stripped:
            break
    data = np.loadtxt(path, comments="#", ndmin=2)
    if "Cd" not in header or "Cl" not in header:
        raise ValueError(f"unexpected coefficient-file columns {header} in {path}")
    return header, np.asarray(data, dtype=np.float64)


def _final_residual(solver_log: str) -> float:
    """The last pressure-equation initial residual reported by simpleFoam."""
    matches = _P_RESIDUAL_RE.findall(solver_log)
    return float(matches[-1]) if matches else float("nan")
