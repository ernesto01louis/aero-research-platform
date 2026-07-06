"""`SU2Solver` — the SU2 v8 CFD adapter (Stage 06).

SU2 is the platform's second concrete solver and its compressible/transonic
workhorse. The adapter implements the `aero.adapters._base.Solver` ABC:

* `prepare` (inherited) writes the case onto the shared NFS dataset,
  delegating to `_write_case`, which builds a native `.su2` mesh and an SU2
  `.cfg` input file;
* `mesh` confirms the generated `.su2` mesh and reports its cell count (SU2
  has no separate in-SIF meshing pass — the mesh is written at `prepare`);
* `run` executes `SU2_CFD` inside the SU2 SIF on a remote LXC via an
  `Executor`;
* `load` parses SU2's `history.csv` into a typed `SolveResult`;
* `wall_distribution` parses `surface_flow.csv` into a `WallDistribution`.

The adapter consumes both the SU2-native specs (`SU2AirfoilSpec`,
`SU2MeshFileSpec`) and the Stage-05 OpenFOAM TMR specs (`CaseSpec`,
`FlatPlateSpec`, `Bump2DSpec`) — so the TMR benchmark cases run through SU2
unchanged. SU2 native quirks are recorded in ADR-006.
"""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

from loguru import logger

from aero.adapters._base import (
    DEFAULT_HOST_NFS_ROOT,
    DEFAULT_REMOTE_NFS_ROOT,
    CaseDir,
    ConvergenceHistory,
    MeshHandle,
    ResultHandle,
    Solver,
    SolveResult,
    SpecLike,
    WallDistribution,
    build_apptainer_exec,
)
from aero.adapters.openfoam.schemas import CaseSpec
from aero.adapters.openfoam.tmr_specs import Bump2DSpec, FlatPlateSpec
from aero.adapters.su2.cfg_writer import write_su2_cfg
from aero.adapters.su2.mesh_writer import (
    airfoil_ogrid,
    bump_grid,
    flat_plate_grid,
    write_su2_mesh,
)
from aero.adapters.su2.schemas import (
    DEFAULT_SU2_SIF_PATH,
    SU2AirfoilSpec,
    SU2MeshFileSpec,
    SU2TurbulenceModel,
)
from aero.orchestration._base import Executor

__all__ = ["SU2Solver"]

_MESH_FILENAME = "mesh.su2"
_CFG_FILENAME = "case.cfg"
_NELEM_RE = re.compile(r"^NELEM=\s*(\d+)", re.MULTILINE)


def _even(n: int) -> int:
    """The next even integer >= `n` — an O-grid i-wrap must close evenly."""
    return n if n % 2 == 0 else n + 1


def _su2_turb(model: str) -> SU2TurbulenceModel:
    """Map the platform turbulence-model name to SU2's keyword."""
    return "SST" if model == "kOmegaSST" else "SA"


class SU2Solver(Solver):
    """Runs an SU2 v8 case through the `prepare -> mesh -> run -> load`
    lifecycle. Concrete implementation of the `Solver` ABC (ADR-006)."""

    def __init__(
        self,
        *,
        sif_path: str = DEFAULT_SU2_SIF_PATH,
        host_nfs_root: Path = DEFAULT_HOST_NFS_ROOT,
        remote_nfs_root: Path = DEFAULT_REMOTE_NFS_ROOT,
        repo_root: Path | None = None,
    ) -> None:
        super().__init__(
            sif_path=sif_path, host_nfs_root=host_nfs_root, remote_nfs_root=remote_nfs_root
        )
        # `repo_root` resolves DVC-tracked `.su2` mesh assets (SU2MeshFileSpec).
        self.repo_root = repo_root

    # --- prepare seam ---------------------------------------------------------
    def _write_case(self, case: SpecLike, host_path: Path) -> None:
        """Write the `.su2` mesh and the SU2 `.cfg` for `case` under `host_path`."""
        host_path.mkdir(parents=True, exist_ok=True)
        mesh_path = host_path / _MESH_FILENAME
        cfg_path = host_path / _CFG_FILENAME

        if isinstance(case, CaseSpec):
            self._write_airfoil(
                mesh_path,
                cfg_path,
                mach=case.mach,
                aoa_deg=case.aoa_deg,
                reynolds=case.reynolds,
                chord=case.chord,
                n_surface=_even(2 * case.n_surface),
                n_normal=case.n_normal,
                radius_chords=case.farfield_extent_chords,
                first_cell_height=case.first_cell_height,
                turbulence_model=_su2_turb(case.turbulence_model),
                iterations=case.end_time,
                cfl=5.0,
            )
        elif isinstance(case, SU2AirfoilSpec):
            self._write_airfoil(
                mesh_path,
                cfg_path,
                mach=case.mach,
                aoa_deg=case.aoa_deg,
                reynolds=case.reynolds,
                chord=case.chord,
                n_surface=_even(case.n_surface),
                n_normal=case.n_normal,
                radius_chords=case.farfield_radius_chords,
                first_cell_height=case.first_cell_height,
                turbulence_model=case.turbulence_model,
                iterations=case.iterations,
                cfl=case.cfl,
            )
        elif isinstance(case, FlatPlateSpec):
            points, quads, markers = flat_plate_grid(
                plate_length=case.plate_length,
                inlet_length=case.inlet_length,
                domain_height=case.domain_height,
                n_streamwise=case.n_streamwise,
                n_inlet=case.n_inlet,
                n_normal=case.n_normal,
                first_cell_height=case.first_cell_height,
            )
            write_su2_mesh(mesh_path, points=points, quads=quads, markers=markers)
            write_su2_cfg(
                cfg_path,
                mach=case.mach,
                aoa_deg=0.0,
                reynolds=case.reynolds,
                ref_length=case.plate_length,
                ref_area=case.plate_length,
                iterations=case.end_time,
                cfl=5.0,
                turbulence_model=_su2_turb(case.turbulence_model),
                n_dim=2,
                wall_markers=("wall",),
                farfield_markers=("farfield", "inlet", "outlet"),
                symmetry_markers=("symmetry",),
                mesh_filename=_MESH_FILENAME,
            )
        elif isinstance(case, Bump2DSpec):
            points, quads, markers = bump_grid(
                bump_length=case.bump_length,
                inlet_length=case.inlet_length,
                outlet_length=case.outlet_length,
                domain_height=case.domain_height,
                bump_height=case.bump_height,
                n_bump=case.n_bump,
                n_inlet=case.n_inlet,
                n_outlet=case.n_outlet,
                n_normal=case.n_normal,
                first_cell_height=case.first_cell_height,
            )
            write_su2_mesh(mesh_path, points=points, quads=quads, markers=markers)
            write_su2_cfg(
                cfg_path,
                mach=case.mach,
                aoa_deg=0.0,
                reynolds=case.reynolds,
                ref_length=case.ref_length,
                ref_area=case.ref_length,
                iterations=case.end_time,
                cfl=5.0,
                turbulence_model=_su2_turb(case.turbulence_model),
                n_dim=2,
                wall_markers=("wall",),
                farfield_markers=("farfield", "inlet", "outlet"),
                symmetry_markers=("symmetry",),
                mesh_filename=_MESH_FILENAME,
            )
        elif isinstance(case, SU2MeshFileSpec):
            self._copy_mesh_asset(case, mesh_path)
            write_su2_cfg(
                cfg_path,
                mach=case.mach,
                aoa_deg=case.aoa_deg,
                reynolds=case.reynolds,
                ref_length=case.ref_length,
                ref_area=case.ref_area,
                iterations=case.iterations,
                cfl=case.cfl,
                turbulence_model=case.turbulence_model,
                n_dim=case.n_dim,
                wall_markers=case.wall_markers,
                farfield_markers=case.farfield_markers,
                symmetry_markers=case.symmetry_markers,
                mesh_filename=_MESH_FILENAME,
            )
        else:
            raise TypeError(f"SU2Solver cannot write a case spec of type {type(case).__name__}")

    def _write_airfoil(
        self,
        mesh_path: Path,
        cfg_path: Path,
        *,
        mach: float,
        aoa_deg: float,
        reynolds: float,
        chord: float,
        n_surface: int,
        n_normal: int,
        radius_chords: float,
        first_cell_height: float,
        turbulence_model: SU2TurbulenceModel,
        iterations: int,
        cfl: float,
    ) -> None:
        """Write an airfoil O-grid `.su2` mesh and its SU2 `.cfg`."""
        points, quads, markers = airfoil_ogrid(
            n_surface=n_surface,
            n_normal=n_normal,
            radius_chords=radius_chords,
            first_cell_height=first_cell_height,
            chord=chord,
        )
        write_su2_mesh(mesh_path, points=points, quads=quads, markers=markers)
        write_su2_cfg(
            cfg_path,
            mach=mach,
            aoa_deg=aoa_deg,
            reynolds=reynolds,
            ref_length=chord,
            ref_area=chord,
            iterations=iterations,
            cfl=cfl,
            turbulence_model=turbulence_model,
            n_dim=2,
            wall_markers=("airfoil",),
            farfield_markers=("farfield",),
            mesh_filename=_MESH_FILENAME,
        )

    def _copy_mesh_asset(self, case: SU2MeshFileSpec, mesh_path: Path) -> None:
        """Copy a DVC-tracked `.su2` mesh asset into the case directory."""
        if self.repo_root is None:
            raise ValueError(
                f"SU2MeshFileSpec {case.name!r} needs a `.su2` asset but SU2Solver "
                "was constructed without `repo_root`"
            )
        src = self.repo_root / case.mesh_file
        if not src.is_file():
            raise FileNotFoundError(
                f"SU2 mesh asset not found: {src} — is the DVC remote pulled (`dvc pull`)?"
            )
        shutil.copyfile(src, mesh_path)

    # --- mesh seam ------------------------------------------------------------
    def mesh(self, case_dir: CaseDir, executor: Executor) -> MeshHandle:
        """Confirm the generated `.su2` mesh and report its cell count.

        SU2 has no separate in-SIF meshing pass — the mesh is written at
        `prepare`. `mesh` validates it and parses `NELEM`. `executor` is unused
        (kept for the `Solver` lifecycle symmetry with OpenFOAM's `blockMesh`).
        """
        del executor  # SU2 meshing is host-side at prepare time
        mesh_file = case_dir.host_path / _MESH_FILENAME
        if not mesh_file.is_file():
            logger.error("SU2 mesh not found: {}", mesh_file)
            return MeshHandle(case_dir=case_dir, ok=False, n_elements=None)
        match = _NELEM_RE.search(mesh_file.read_text(encoding="utf-8"))
        n_elements = int(match.group(1)) if match else None
        ok = n_elements is not None and n_elements > 0
        if not ok:
            logger.error("SU2 mesh {} has no NELEM count", mesh_file)
        return MeshHandle(case_dir=case_dir, ok=ok, n_elements=n_elements)

    # --- run seam -------------------------------------------------------------
    def run(self, case_dir: CaseDir, executor: Executor) -> ResultHandle:
        """Run `SU2_CFD` inside the SU2 SIF (long-running, via the executor).

        SU2 v8 is built with `--with-mpi=enabled`, so `MPI_Init` always runs
        even on a single rank. In the unprivileged-LXC nested user namespace,
        OpenMPI's default TCP-BTL + OOB-TCP startup hits the same socket EPERM
        that blocked buildah's image pull (handoff §1a), surfacing as
        `opal_ifinit: socket() failed with errno=13` and crashing the solver
        with `rc=53`. The env-var overrides force OpenMPI onto the self +
        shared-memory transports and off the TCP out-of-band channel — all
        single-node, no kernel socket use. `--writable-tmpfs` gives OpenMPI a
        session-dir under `/tmp`.
        """
        command = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=str(case_dir.remote_path),
            command=f"SU2_CFD {_CFG_FILENAME}",
            writable_tmpfs=True,
            env={
                "OMPI_MCA_btl": "self,sm",
                "OMPI_MCA_oob": "^tcp",
                "OMPI_MCA_btl_base_warn_component_unused": "0",
            },
        )
        result = executor.run(command, long_running=True, session=f"su2-{case_dir.run_id}")
        if not result.ok:
            logger.error("SU2_CFD failed (rc={})", result.returncode)
        return ResultHandle(
            case_dir=case_dir,
            returncode=result.returncode,
            output_host_path=case_dir.host_path,
            solver_log=result.stdout,
        )

    # --- load seam ------------------------------------------------------------
    def load(self, result: ResultHandle) -> SolveResult:
        """Parse SU2's `history.csv` into a typed `SolveResult`.

        SU2 writes a columnar `history.csv` (one row per iteration); the
        monitored-residual `ConvergenceHistory` is the `rms[Rho]` column —
        SU2 reports it base-10-log-scaled, which is recorded as-is (Invariant 7
        asks for the *monitored* residual, per solver).
        """
        history_csv = result.output_host_path / "history.csv"
        rows = _read_su2_csv(history_csv)
        if not rows:
            raise ValueError(f"SU2 history.csv has no data rows: {history_csv}")

        iter_key = _find_key(rows[0], "Inner_Iter", "Time_Iter", "Iteration")
        rms_key = _find_key(rows[0], "rms[Rho]", "rms[Rho_0]", "rms[Density]")
        cd_key = _find_key(rows[0], "CD", "CD(MARKER_MONITORING)")
        cl_key = _find_key(rows[0], "CL", "CL(MARKER_MONITORING)")

        iterations = [int(float(r[iter_key])) for r in rows]
        residuals = [float(r[rms_key]) for r in rows]
        return SolveResult(
            run_id=result.case_dir.run_id,
            case_name=result.case_dir.spec.name,
            cd=float(rows[-1][cd_key]),
            cl=float(rows[-1][cl_key]),
            iterations_to_convergence=iterations[-1] + 1,
            final_residual=residuals[-1],
            history=ConvergenceHistory(iteration=tuple(iterations), residual=tuple(residuals)),
            source=str(history_csv),
        )

    # --- wall-distribution seam ----------------------------------------------
    def wall_distribution(
        self, result: ResultHandle, *, patch: str = "wall", u_inf: float = 1.0
    ) -> WallDistribution:
        """Parse SU2's `surface_flow.csv` into a `WallDistribution`.

        `MARKER_PLOTTING` is the no-slip wall, so `surface_flow.csv` is exactly
        that patch; the rows are sorted ascending in the streamwise coordinate.
        """
        surface_csv = result.output_host_path / "surface_flow.csv"
        rows = _read_su2_csv(surface_csv)
        if not rows:
            raise ValueError(f"SU2 surface_flow.csv has no data rows: {surface_csv}")

        x_key = _find_key(rows[0], "x", "Coord_x", "Coordinate_x")
        cp_key = _find_key(rows[0], "Pressure_Coefficient", "C_p", "Cp")
        cf_key = _find_key(rows[0], "Skin_Friction_Coefficient_x", "Skin_Friction_Coefficient")
        triples = sorted((float(r[x_key]), float(r[cp_key]), float(r[cf_key])) for r in rows)
        return WallDistribution(
            patch=patch,
            x=[t[0] for t in triples],
            cp=[t[1] for t in triples],
            cf=[t[2] for t in triples],
        )


def _read_su2_csv(path: Path) -> list[dict[str, str]]:
    """Read an SU2 CSV (`history.csv` / `surface_flow.csv`), cleaning header keys.

    SU2 quotes header names and pads them with spaces; the keys are stripped of
    quotes and whitespace so callers can match on the bare field name.
    """
    if not path.is_file():
        raise FileNotFoundError(f"SU2 output file not found: {path} — did SU2_CFD run?")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        rows = [r for r in reader if r]
    if len(rows) < 2:
        return []
    header = [c.strip().strip('"').strip() for c in rows[0]]
    return [dict(zip(header, (c.strip() for c in r), strict=False)) for r in rows[1:]]


def _find_key(row: dict[str, str], *candidates: str) -> str:
    """The first `candidates` key present in `row` — fail loud if none match."""
    for cand in candidates:
        if cand in row:
            return cand
    raise KeyError(f"none of {candidates} found in SU2 output columns {sorted(row)}")
