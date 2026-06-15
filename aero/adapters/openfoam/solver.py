"""`OpenFOAMSolver` — the OpenFOAM-ESI CFD adapter.

The pipeline is `prepare -> mesh -> run -> load`:

* `prepare` (inherited from `Solver`) writes an OpenFOAM case onto the shared
  NFS dataset, delegating the case-file writing to `_write_case`;
* `mesh` and `run` execute `blockMesh` / `simpleFoam` inside the OpenFOAM SIF
  on a remote LXC, through an `Executor`;
* `load` parses the force-coefficient output into a typed `SolveResult`;
* `wall_distribution` parses the sampled-surface output into a
  `WallDistribution` (Cf/Cp along a wall patch).

Stage 06 refactored this adapter onto the `aero.adapters._base.Solver` ABC when
SU2 became the second solver and forced the shared abstraction (ADR-006). The
OpenFOAM-specific code — the `blockMesh`/`simpleFoam` commands, the polyMesh
check, the `coefficient.dat`/`raw` parsers — stays here; the lifecycle skeleton
and the shared handle/result types live in `_base`.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
from loguru import logger

from aero.adapters._base import (
    DEFAULT_HOST_NFS_ROOT,
    DEFAULT_REMOTE_NFS_ROOT,
    ConvergenceHistory,
    MeshHandle,
    ResultHandle,
    Solver,
    SolveResult,
    SpecLike,
    WallDistribution,
    build_apptainer_exec,
)
from aero.adapters._base import (
    CaseDir as CaseDir,  # re-exported for backward-compatible imports
)
from aero.adapters.openfoam._foam_common import RHO_INF, U_INF
from aero.adapters.openfoam.case_writer import write_case
from aero.adapters.openfoam.fields import extract_wall_distributions
from aero.adapters.openfoam.schemas import DEFAULT_SIF_PATH, CaseSpec
from aero.adapters.openfoam.tmr_case_writer import write_tmr_case
from aero.adapters.openfoam.tmr_specs import Bump2DSpec, FlatPlateSpec
from aero.orchestration._base import Executor

# `build_apptainer_exec` moved to `_base` in Stage 06 (it is solver-neutral);
# it is re-exported here so the Stage-03 adapter unit tests keep importing it
# from `aero.adapters.openfoam.solver`.
__all__ = ["OpenFOAMSolver", "build_apptainer_exec"]

_CELL_COUNT_RE = re.compile(r"nCells:\s*(\d+)")
_P_RESIDUAL_RE = re.compile(r"Solving for p,\s*Initial residual\s*=\s*([0-9.eE+-]+)")


class OpenFOAMSolver(Solver):
    """Runs an OpenFOAM-ESI case through the `prepare -> mesh -> run -> load`
    lifecycle. Concrete implementation of the `Solver` ABC (ADR-006)."""

    def __init__(
        self,
        *,
        sif_path: str = DEFAULT_SIF_PATH,
        host_nfs_root: Path = DEFAULT_HOST_NFS_ROOT,
        remote_nfs_root: Path = DEFAULT_REMOTE_NFS_ROOT,
    ) -> None:
        super().__init__(
            sif_path=sif_path, host_nfs_root=host_nfs_root, remote_nfs_root=remote_nfs_root
        )

    def _write_case(self, case: SpecLike, host_path: Path) -> None:
        """Write the OpenFOAM case files under `host_path`.

        Dispatches on the spec type: an airfoil `CaseSpec` is written by the
        C-grid `write_case`; a TMR geometry spec by `write_tmr_case`. An
        unrecognised spec fails loud — the OpenFOAM adapter does not run SU2
        (or any other) case specs.
        """
        if isinstance(case, CaseSpec):
            write_case(case, host_path)
        elif isinstance(case, FlatPlateSpec | Bump2DSpec):
            write_tmr_case(case, host_path)
        else:
            raise TypeError(
                f"OpenFOAMSolver cannot write a case spec of type {type(case).__name__}"
            )

    def mesh(self, case_dir: CaseDir, executor: Executor) -> MeshHandle:
        """Run `blockMesh` inside the SIF, then confirm a polyMesh was written.

        `mesh` takes the `Executor` as an argument (like `run`); meshing
        executes inside the SIF on a remote host exactly as the solve does —
        the symmetry is recorded in ADR-003.
        """
        command = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=str(case_dir.remote_path),
            command="blockMesh",
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
            n_elements=int(cells.group(1)) if cells else None,
        )

    def run(self, case_dir: CaseDir, executor: Executor) -> ResultHandle:
        """Run `simpleFoam` inside the SIF (long-running, via the executor)."""
        command = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=str(case_dir.remote_path),
            command="simpleFoam",
        )
        result = executor.run(command, long_running=True, session=f"sf-{case_dir.run_id}")
        if not result.ok:
            logger.error("simpleFoam failed (rc={})", result.returncode)
        return ResultHandle(
            case_dir=case_dir,
            returncode=result.returncode,
            output_host_path=case_dir.host_path / "postProcessing",
            solver_log=result.stdout,
        )

    def load(self, result: ResultHandle) -> SolveResult:
        """Parse the `forceCoeffs` output into a typed `SolveResult`.

        The `forceCoeffs` function object writes a columnar `coefficient.dat`
        (not a field file), so this parses with `numpy.loadtxt`. The
        monitored-residual `ConvergenceHistory` is the per-iteration sequence of
        `simpleFoam` pressure-equation initial residuals (Invariant 7).
        """
        coeff_file = _coefficient_file(result.output_host_path)
        columns, data = _read_coefficient_dat(coeff_file)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        iteration = data[:, columns.index("Time")].astype(int)
        cd = data[:, columns.index("Cd")]
        cl = data[:, columns.index("Cl")]

        residuals = _p_residuals(result.solver_log)
        if not residuals:
            raise ValueError(
                f"no pressure-equation residuals in the simpleFoam log for "
                f"{result.case_dir.run_id} — did the solve run?"
            )
        history = ConvergenceHistory(
            iteration=tuple(range(1, len(residuals) + 1)),
            residual=tuple(residuals),
        )

        # Pressure/viscous drag decomposition from the `forces` function object,
        # if the case wrote one (airfoil cases do — flat-plate / bump use
        # wall_distribution instead). The hypothesis under test for NACA 0012 is
        # "the excess Cd is pressure drag, not friction"; without this the harness
        # could only see total Cd. None for cases that emit no force.dat.
        cd_total = float(cd[-1])
        cd_pressure, cd_viscous = self._drag_decomposition(result, cd_total)

        return SolveResult(
            run_id=result.case_dir.run_id,
            case_name=result.case_dir.spec.name,
            cd=cd_total,
            cl=float(cl[-1]),
            cd_pressure=cd_pressure,
            cd_viscous=cd_viscous,
            iterations_to_convergence=int(iteration[-1]),
            final_residual=residuals[-1],
            history=history,
            source=str(coeff_file),
        )

    def _drag_decomposition(
        self, result: ResultHandle, cd_total: float
    ) -> tuple[float | None, float | None]:
        """(cd_pressure, cd_viscous) from the `forces` FO, or (None, None).

        Projects the pressure- and viscous-force vectors onto the drag direction
        (cos(aoa), sin(aoa)) and divides by the dynamic pressure x reference area
        (0.5 * rhoInf * magUInf^2 * Aref). FAIL-LOUD: if the two components do
        not reconstruct the forceCoeffs total Cd, the force.dat layout was not
        what we parsed — raise rather than report a wrong split.
        """
        force_file = _maybe_force_file(result.output_host_path)
        if force_file is None:
            return None, None
        spec = result.case_dir.spec
        aoa = math.radians(float(getattr(spec, "aoa_deg", 0.0)))
        drag_dir = (math.cos(aoa), math.sin(aoa))
        a_ref = float(getattr(spec, "chord", 1.0)) * float(getattr(spec, "span", 1.0))
        q_aref = 0.5 * RHO_INF * U_INF**2 * a_ref
        cd_pressure, cd_viscous = _read_force_decomposition(
            force_file, drag_dir=drag_dir, q_aref=q_aref
        )
        recon = cd_pressure + cd_viscous
        # generous band: parser/format error shows up as a gross mismatch, not a
        # rounding wobble, so 1e-3 absolute + 1% relative cannot mask a real bug.
        if abs(recon - cd_total) > 1.0e-3 + 1.0e-2 * abs(cd_total):
            raise ValueError(
                f"force decomposition cd_pressure+cd_viscous={recon:.6g} disagrees with "
                f"forceCoeffs total cd={cd_total:.6g} for {result.case_dir.run_id} — "
                f"unexpected force.dat layout in {force_file}"
            )
        return cd_pressure, cd_viscous

    def wall_distribution(self, result: ResultHandle, *, patch: str = "wall") -> WallDistribution:
        """Extract the Cf/Cp distribution along wall `patch` from a finished solve.

        Delegates to the OpenFOAM-specific `extract_wall_distributions` parser,
        which reads the `surfaces` function-object `raw` output.
        """
        return extract_wall_distributions(result.output_host_path, patch=patch)


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


def _maybe_force_file(post_processing: Path) -> Path | None:
    """Locate the `forces` FO `force.dat` under a postProcessing tree, or None.

    Returns None when the case wrote no `forces1` output (e.g. flat-plate / bump,
    which use wall_distribution instead) so the loader leaves the decomposition
    unset rather than failing.
    """
    for name in ("force.dat", "forces.dat"):
        hits = sorted(post_processing.glob(f"forces1/*/{name}"))
        if hits:
            return hits[0]
    return None


def _read_force_decomposition(
    path: Path, *, drag_dir: tuple[float, float], q_aref: float
) -> tuple[float, float]:
    """(cd_pressure, cd_viscous) from an OpenFOAM `forces` force.dat last row.

    Handles both output layouts the `forces` FO has used: the parenthesised
    vector form ``((Fp_x Fp_y Fp_z) (Fv_x Fv_y Fv_z) ...) (moments...)`` where
    the first two triples are the pressure and viscous force vectors, and the
    flat-column ESI form ``Time total(3) pressure(3) viscous(3) [porous(3)]``.
    The caller (`_drag_decomposition`) FAIL-LOUD-checks the result against the
    independently-computed total Cd, so a mis-parsed layout cannot pass silently.
    """
    last: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            last = stripped
    if last is None:
        raise ValueError(f"no data rows in forces file {path}")

    if "(" in last:
        triples = re.findall(r"\(([^()]*)\)", last)
        if len(triples) < 2:
            raise ValueError(f"unexpected parenthesised forces layout in {path}: {last!r}")
        fp = [float(v) for v in triples[0].split()]
        fv = [float(v) for v in triples[1].split()]
    else:
        nums = [float(v) for v in last.split()]
        # flat ESI: Time, total(3), pressure(3), viscous(3), [porous(3)]
        if len(nums) < 10:
            raise ValueError(f"unexpected flat forces layout in {path}: {last!r}")
        fp = nums[4:7]
        fv = nums[7:10]

    cd_pressure = (fp[0] * drag_dir[0] + fp[1] * drag_dir[1]) / q_aref
    cd_viscous = (fv[0] * drag_dir[0] + fv[1] * drag_dir[1]) / q_aref
    return cd_pressure, cd_viscous


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


def _p_residuals(solver_log: str) -> list[float]:
    """The per-iteration pressure-equation initial residuals from a solve log."""
    return [float(m) for m in _P_RESIDUAL_RE.findall(solver_log)]
