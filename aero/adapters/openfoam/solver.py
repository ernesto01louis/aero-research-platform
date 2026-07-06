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
    TimeHistory,
    WallDistribution,
    build_apptainer_exec,
)
from aero.adapters._base import (
    CaseDir as CaseDir,  # re-exported for backward-compatible imports
)
from aero.adapters.openfoam._foam_common import RHO_INF, U_INF
from aero.adapters.openfoam.case_writer import write_case
from aero.adapters.openfoam.cylinder import CylinderSpec, write_cylinder_case
from aero.adapters.openfoam.fields import extract_wall_distributions
from aero.adapters.openfoam.plunging_airfoil import (
    PlungingAirfoilSpec,
    write_plunging_airfoil_case,
)
from aero.adapters.openfoam.schemas import DEFAULT_SIF_PATH, CaseSpec
from aero.adapters.openfoam.t3a import T3ASpec, write_t3a_case
from aero.adapters.openfoam.tmr_case_writer import write_tmr_case
from aero.adapters.openfoam.tmr_specs import Bump2DSpec, FlatPlateSpec
from aero.orchestration._base import Executor
from aero.postprocess._base import Signal
from aero.postprocess.cycle_detection import detect_cycle_convergence
from aero.postprocess.efficiency import MotionKinematics, propulsive_metrics
from aero.postprocess.forces import ForceDecomposition, decompose_drag
from aero.postprocess.frequency import strouhal as _pp_strouhal
from aero.postprocess.phase_averaging import segment_cycles

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
        elif isinstance(case, CylinderSpec):
            write_cylinder_case(case, host_path)
        elif isinstance(case, PlungingAirfoilSpec):
            write_plunging_airfoil_case(case, host_path)
        elif isinstance(case, T3ASpec):
            write_t3a_case(case, host_path)
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
        """Run the OpenFOAM solver inside the SIF (long-running, via the executor).

        Steady cases run `simpleFoam`; a transient case (`spec.transient`, e.g.
        the vortex-shedding cylinder) runs `pimpleFoam`.
        """
        app = "pimpleFoam" if getattr(case_dir.spec, "transient", False) else "simpleFoam"
        command = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=str(case_dir.remote_path),
            command=app,
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

        A transient case (`spec.transient`) takes a different path: the lift
        coefficient is a time series, and the result carries a `TimeHistory`
        plus the FFT-derived Strouhal number (vortex shedding).
        """
        if getattr(result.case_dir.spec, "motion", None) is not None:
            return self._load_moving(result)
        if getattr(result.case_dir.spec, "transient", False):
            return self._load_transient(result)

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
        # Closure is now a schema invariant (aero.postprocess.forces.ForceDecomposition):
        # its validator uses the same 1e-3 absolute + 1% relative band. A parser/format
        # error shows up as a gross mismatch, not a rounding wobble, so it cannot mask a
        # real bug. Wrap the failure to preserve the adapter's file-pointing message.
        try:
            fd = ForceDecomposition(total=cd_total, pressure=cd_pressure, viscous=cd_viscous)
        except ValueError as exc:
            raise ValueError(
                f"force decomposition cd_pressure+cd_viscous={cd_pressure + cd_viscous:.6g} "
                f"disagrees with forceCoeffs total cd={cd_total:.6g} for "
                f"{result.case_dir.run_id} — unexpected force.dat layout in {force_file}"
            ) from exc
        return fd.pressure, fd.viscous

    def _load_transient(self, result: ResultHandle) -> SolveResult:
        """Parse a transient `forceCoeffs` time series into a `SolveResult`.

        Reads the full Cl(t) history, drops the initial transient (the shedding
        instability takes ~half the run to saturate), FFTs the saturated tail to
        recover the dominant shedding frequency, and reports the Strouhal number
        St = f D / U in `scalars`. `history` is the lift-coefficient TimeHistory;
        `cd`/`cl` are the post-transient time means.
        """
        spec = result.case_dir.spec
        coeff_file = _coefficient_file(result.output_host_path)
        columns, data = _read_coefficient_dat(coeff_file)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        t = data[:, columns.index("Time")]
        cd = data[:, columns.index("Cd")]
        cl = data[:, columns.index("Cl")]
        if len(t) < 16:
            raise ValueError(
                f"transient solve {result.case_dir.run_id} wrote only {len(t)} force samples "
                "— too few to resolve a shedding frequency (did pimpleFoam run to endTime?)"
            )
        # Saturated tail: drop the first half (instability growth + transient).
        start = len(t) // 2
        t_w, cl_w, cd_w = t[start:], cl[start:], cd[start:]
        diameter = float(getattr(spec, "diameter", 1.0))
        strouhal = _strouhal_from_signal(t_w, cl_w, diameter=diameter, u_inf=U_INF)
        history = TimeHistory(
            t=tuple(float(v) for v in t_w),
            monitor=tuple(float(v) for v in cl_w),
            monitor_name="lift_coefficient",
        )
        return SolveResult(
            run_id=result.case_dir.run_id,
            case_name=spec.name,
            cd=float(cd_w.mean()),
            cl=float(cl_w.mean()),
            iterations_to_convergence=len(t),
            final_residual=float(cl_w.std()),  # shedding amplitude (RMS lift)
            history=history,
            scalars={"strouhal": strouhal},
            source=str(coeff_file),
        )

    def _load_moving(self, result: ResultHandle) -> SolveResult:
        """Parse a MOVING-mesh (morphing) transient solve into a `SolveResult`.

        Cycle-segments the lift trace over the forcing period, checks periodic steady
        state (FAIL-LOUD if not converged — a non-converged number is not reportable,
        the Stage-11 NO-GO discipline), recovers the response Strouhal over the converged
        tail (for the oscillating cylinder this equals the forcing frequency = lock-in),
        and reports the cycle-mean pressure/viscous drag split. A plunging airfoil (chord,
        no diameter) additionally reports thrust / power / propulsive efficiency from the
        total aerodynamic force history over the converged cycles.
        """
        spec = result.case_dir.spec
        motion = getattr(spec, "motion", None)
        assert motion is not None  # the load() dispatch guarantees a moving spec
        period = 1.0 / float(motion.frequency)

        coeff_file = _coefficient_file(result.output_host_path)
        columns, data = _read_coefficient_dat(coeff_file)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        t = data[:, columns.index("Time")]
        cd = data[:, columns.index("Cd")]
        cl = data[:, columns.index("Cl")]
        keep = _strictly_increasing_mask(t)  # dedupe duplicate FO timestamps (write boundaries)
        t, cd, cl = t[keep], cd[keep], cl[keep]
        if len(t) < 16:
            raise ValueError(
                f"moving solve {result.case_dir.run_id} wrote only {len(t)} force samples "
                "— too few to segment cycles (did pimpleFoam run to endTime?)"
            )

        samples = segment_cycles(Signal.from_arrays(t, cl, name="lift_coefficient"), period=period)
        conv = detect_cycle_convergence(samples)
        if not conv.converged:
            raise ValueError(
                f"moving case {result.case_dir.run_id} did not reach a periodic steady "
                f"state (mean_drift={conv.mean_drift:.3g}, amplitude_drift="
                f"{conv.amplitude_drift:.3g} over {conv.n_cycles} cycles) — not reportable "
                "(Stage-11 NO-GO discipline; investigate motion/mesh/time-resolution)"
            )

        t_start = float(t[0]) + conv.converged_from_cycle * period
        tail = t >= t_start - 1.0e-12
        length_ref = float(getattr(spec, "diameter", getattr(spec, "chord", 1.0)))
        st = _pp_strouhal(
            Signal.from_arrays(t[tail], cl[tail], name="lift_coefficient"),
            length=length_ref,
            velocity=U_INF,
        ).strouhal
        assert st is not None

        scalars: dict[str, float] = {
            "strouhal": st,
            "cycle_converged": 1.0,
            "n_converged_cycles": float(conv.n_converged_cycles),
            "converged_from_cycle": float(conv.converged_from_cycle),
            "mean_drift": conv.mean_drift,
            "amplitude_drift": conv.amplitude_drift,
            "forcing_period": period,
        }

        # Cycle-mean pressure/viscous drag split (moving cases write a `forces` FO); and,
        # for a plunging airfoil, thrust / power / propulsive efficiency.
        cd_pressure: float | None = None
        cd_viscous: float | None = None
        force_file = _maybe_force_file(result.output_host_path)
        if force_file is not None:
            ft, fp, fv = _read_force_history(force_file)
            ftail = ft >= t_start - 1.0e-12
            aoa = math.radians(
                float(getattr(spec, "aoa_deg", getattr(spec, "inflow_angle_deg", 0.0)))
            )
            drag_dir = (math.cos(aoa), math.sin(aoa))
            a_ref = length_ref * float(getattr(spec, "span", 1.0))
            q_aref = 0.5 * RHO_INF * U_INF**2 * a_ref
            fd = decompose_drag(
                pressure_force=(float(fp[ftail, 0].mean()), float(fp[ftail, 1].mean())),
                viscous_force=(float(fv[ftail, 0].mean()), float(fv[ftail, 1].mean())),
                direction=drag_dir,
                q_aref=q_aref,
                total=float(cd[tail].mean()),
            )
            cd_pressure, cd_viscous = fd.pressure, fd.viscous

            # A plunging airfoil (has chord, no diameter) is a propulsor: report thrust,
            # input power, and propulsive efficiency over the converged cycles.
            is_foil = getattr(spec, "chord", None) is not None and not hasattr(spec, "diameter")
            if is_foil:
                metrics = propulsive_metrics(
                    fx=Signal.from_arrays(ft[ftail], fp[ftail, 0] + fv[ftail, 0], name="fx"),
                    fy=Signal.from_arrays(ft[ftail], fp[ftail, 1] + fv[ftail, 1], name="fy"),
                    kin=MotionKinematics(amplitude=float(motion.amplitude), omega=motion.omega),
                    rho=RHO_INF,
                    u_inf=U_INF,
                    ref_area=a_ref,
                )
                scalars["thrust_coefficient"] = metrics.thrust_coefficient
                scalars["power_coefficient"] = metrics.power_coefficient
                scalars["strouhal_heave"] = metrics.strouhal
                if metrics.propulsive_efficiency is not None:
                    scalars["propulsive_efficiency"] = metrics.propulsive_efficiency

        history = TimeHistory(
            t=tuple(float(v) for v in t[tail]),
            monitor=tuple(float(v) for v in cl[tail]),
            monitor_name="lift_coefficient",
        )
        return SolveResult(
            run_id=result.case_dir.run_id,
            case_name=spec.name,
            cd=float(cd[tail].mean()),
            cl=float(cl[tail].mean()),
            cd_pressure=cd_pressure,
            cd_viscous=cd_viscous,
            iterations_to_convergence=len(t),
            final_residual=float(cl[tail].std()),
            history=history,
            scalars=scalars,
            source=str(coeff_file),
        )

    def wall_distribution(
        self, result: ResultHandle, *, patch: str = "wall", u_inf: float = U_INF
    ) -> WallDistribution:
        """Extract the Cf/Cp distribution along wall `patch` from a finished solve.

        Delegates to the OpenFOAM-specific `extract_wall_distributions` parser,
        which reads the `surfaces` function-object `raw` output. `u_inf` is the
        reference speed for the Cp/Cf non-dimensionalisation (default 1.0, the
        platform convention); the dimensional T3A case passes its 5.4 m/s.
        """
        return extract_wall_distributions(result.output_host_path, patch=patch, u_inf=u_inf)


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


def _strictly_increasing_mask(t: np.ndarray) -> np.ndarray:
    """Boolean mask keeping only rows whose time strictly exceeds all earlier times.

    OpenFOAM force/forceCoeffs FO output can carry **duplicate timestamps**: with
    ``adjustTimeStep`` + ``adjustableRunTime`` writes the solver takes a sub-step to land
    exactly on a write time, and the FO records both at the same (written-precision) time
    (a restart can also re-append). A ``Signal`` needs strictly-ascending time, so dedupe
    by keeping the first row at each new maximum time. (Frequent writes — e.g. the foil's
    0.02 interval — trigger this; the cylinder's 0.1 interval did not.)
    """
    if len(t) == 0:
        return np.zeros(0, dtype=bool)
    run_max = np.maximum.accumulate(t)
    keep = np.empty(len(t), dtype=bool)
    keep[0] = True
    keep[1:] = t[1:] > run_max[:-1]
    return keep


def _read_force_history(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(times, pressure_xy, viscous_xy) time series from a `forces` FO `force.dat`.

    Handles both layouts (parenthesised vector form and the flat ESI columns) the
    Stage-10 `_read_force_decomposition` parses, but for every row (a time series, not
    just the last row) — the moving cases need the full history for cycle-mean forces and
    the plunging-foil thrust/power integrals. Returns numpy arrays: ``t`` (N,),
    ``pressure`` (N,2), ``viscous`` (N,2) — the in-plane (x, y) components.
    """
    times: list[float] = []
    pressures: list[list[float]] = []
    viscous: list[list[float]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "(" in s:
            t = float(s.split("(", 1)[0].split()[0])
            triples = re.findall(r"\(([^()]*)\)", s)
            if len(triples) < 2:
                raise ValueError(f"unexpected parenthesised forces layout in {path}: {s!r}")
            fp = [float(v) for v in triples[0].split()]
            fv = [float(v) for v in triples[1].split()]
        else:
            nums = [float(v) for v in s.split()]
            if len(nums) < 10:
                raise ValueError(f"unexpected flat forces layout in {path}: {s!r}")
            t, fp, fv = nums[0], nums[4:7], nums[7:10]
        times.append(t)
        pressures.append(fp[:2])
        viscous.append(fv[:2])
    if not times:
        raise ValueError(f"no data rows in forces file {path}")
    t_arr = np.asarray(times, dtype=np.float64)
    fp_arr = np.asarray(pressures, dtype=np.float64)
    fv_arr = np.asarray(viscous, dtype=np.float64)
    keep = _strictly_increasing_mask(t_arr)  # dedupe duplicate FO timestamps
    return t_arr[keep], fp_arr[keep], fv_arr[keep]


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


def _strouhal_from_signal(t: np.ndarray, cl: np.ndarray, *, diameter: float, u_inf: float) -> float:
    """Strouhal number from a lift-coefficient time series via FFT.

    Stage 11 promoted the FFT + parabolic-peak-interpolation helper into the
    solver-agnostic ``aero.postprocess.frequency`` toolkit (identical math, so the
    Stage-10 cylinder result is preserved). This thin wrapper is kept so the
    Stage-03/10 adapter unit tests keep importing it from this module.
    """
    est = _pp_strouhal(
        Signal.from_arrays(t, cl, name="lift_coefficient"), length=diameter, velocity=u_inf
    )
    st = est.strouhal
    assert st is not None  # strouhal() always populates it
    return st
