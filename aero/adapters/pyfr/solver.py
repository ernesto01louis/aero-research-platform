"""PyFR adapter — `PyFRSolver` satisfying the Stage-07 `Solver` ABC.

The lifecycle:

1. `prepare`  — the base-class template method; calls `_write_case` to
                drop `mesh.msh2` + `solver.ini` onto the NFS dataset.
2. `mesh`     — runs `pyfr import mesh.msh2 mesh.pyfrm` inside the SIF
                (and `pyfr partition` if `mpi_n > 1`). Validates that
                `mesh.pyfrm` lands; counts `n_elements` from the spec and
                derives `n_dof`.
3. `run`      — runs `pyfr run -b cuda solver.ini mesh.pyfrm` inside the
                SIF with `--nv` (gpu=True). Long-running (Taylor-Green
                t_end=20.0 at dt=1e-3 = 20k steps).
4. `load`     — parses `out/integrate.csv` (per-step KE/enstrophy) into a
                typed `TimeHistory(monitor_name="dissipation_rate")` and a
                `SolveResult` with the peak dissipation in `.scalars`.
5. `wall_distribution` — raises `NotImplementedError` for periodic cases
                          (Taylor-Green has no wall); periodic-hill case
                          extraction is a Stage-12 follow-up.

Stage-07 protocol surface used: `MeshHandle(n_elements, n_dof)`,
`SolveResult(cd=None, cl=None, scalars=..., history=TimeHistory(...))`,
`build_apptainer_exec(gpu=True, mpi_n=N)`.
"""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

import numpy as np
from loguru import logger

from aero.adapters._base import (
    DEFAULT_HOST_NFS_ROOT,
    DEFAULT_REMOTE_NFS_ROOT,
    CaseDir,
    MeshHandle,
    ResultHandle,
    Solver,
    SolveResult,
    SpecLike,
    TimeHistory,
    WallDistribution,
    build_apptainer_exec,
)
from aero.adapters._meshing.gmsh_high_order import write_taylor_green_msh2
from aero.adapters.pyfr.case_writer import write_taylor_green_ini
from aero.adapters.pyfr.schemas import (
    DEFAULT_PYFR_SIF_PATH,
    PyFRMeshFileSpec,
    PyFRTaylorGreenSpec,
)
from aero.orchestration._base import Executor

_MESH_MSH = "mesh.msh2"
_MESH_PYFRM = "mesh.pyfrm"
_SOLVER_INI = "solver.ini"
_INTEGRATE_CSV = "out/integrate.csv"

# `pyfr import` doesn't print a stable element-count line, so we re-derive
# n_elements from the spec. For mesh-file cases we parse the gmsh `$Elements`
# header on the host. Both paths land before `mesh()`.
_PYFRM_OK_PATTERN = re.compile(r"\bImported\b", re.IGNORECASE)


class PyFRSolver(Solver):
    """The PyFR `Solver` — Stage 07's third concrete adapter.

    Both `PyFRTaylorGreenSpec` and `PyFRMeshFileSpec` dispatch through
    `_write_case`. The same SIF handles both: the only differences are the
    mesh-file source (generated vs. DVC-tracked) and which `solver.ini`
    template we render.
    """

    def __init__(
        self,
        *,
        sif_path: str = DEFAULT_PYFR_SIF_PATH,
        host_nfs_root: Path = DEFAULT_HOST_NFS_ROOT,
        remote_nfs_root: Path = DEFAULT_REMOTE_NFS_ROOT,
        repo_root: Path | None = None,
        mpi_n: int | None = None,
    ) -> None:
        super().__init__(
            sif_path=sif_path,
            host_nfs_root=host_nfs_root,
            remote_nfs_root=remote_nfs_root,
        )
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.mpi_n = mpi_n  # None = single-rank single-GPU; > 1 = multi-rank

    # --- write-case seam ------------------------------------------------------
    def _write_case(self, case: SpecLike, host_path: Path) -> None:
        host_path.mkdir(parents=True, exist_ok=True)
        if isinstance(case, PyFRTaylorGreenSpec):
            n_hex = write_taylor_green_msh2(
                host_path / _MESH_MSH,
                n_elements_per_dir=case.n_elements_per_dir,
            )
            write_taylor_green_ini(
                host_path / _SOLVER_INI,
                case,
                mesh_filename=_MESH_PYFRM,
            )
            (host_path / "out").mkdir(parents=True, exist_ok=True)
            logger.info(
                "wrote PyFR Taylor-Green case at {} ({} hex elements, p={})",
                host_path,
                n_hex,
                case.polynomial_order,
            )
            return
        if isinstance(case, PyFRMeshFileSpec):
            if self.repo_root is None:
                raise ValueError(
                    "PyFRMeshFileSpec requires repo_root on PyFRSolver(...) "
                    "to locate the DVC-tracked mesh + ini template."
                )
            src_mesh = self.repo_root / case.mesh_file
            src_ini = self.repo_root / case.cfg_template
            if not src_mesh.is_file():
                raise FileNotFoundError(
                    f"PyFR mesh asset missing: {src_mesh} — did you `dvc pull` the asset?"
                )
            if not src_ini.is_file():
                raise FileNotFoundError(f"PyFR ini template missing: {src_ini}")
            shutil.copyfile(src_mesh, host_path / _MESH_MSH)
            shutil.copyfile(src_ini, host_path / _SOLVER_INI)
            (host_path / "out").mkdir(parents=True, exist_ok=True)
            logger.info("wrote PyFR mesh-file case at {}", host_path)
            return
        raise TypeError(
            f"PyFRSolver._write_case cannot handle spec of type {type(case).__name__}; "
            "expected PyFRTaylorGreenSpec or PyFRMeshFileSpec"
        )

    # --- mesh seam -----------------------------------------------------------
    def mesh(self, case_dir: CaseDir, executor: Executor) -> MeshHandle:
        """Run `pyfr import` (and `pyfr partition` if multi-rank) inside the SIF.

        Element + DOF counts are re-derived from the spec; PyFR does not
        emit a parse-friendly count line. The structured Taylor-Green spec
        gives `N^3` hex elements; for a mesh-file spec we parse the gmsh
        header on the host. p+1 is the per-direction node count for FR,
        so `n_dof = n_elements * (p+1)^3`.
        """
        spec = case_dir.spec
        # 1. pyfr import (host-side mesh -> pyfr native). CPU-only.
        import_cmd = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=str(case_dir.remote_path),
            command=f"pyfr import -t gmsh {_MESH_MSH} {_MESH_PYFRM}",
            gpu=False,
        )
        result = executor.run(import_cmd, timeout_s=900)
        if not result.ok:
            logger.error("pyfr import failed (rc={}):\n{}", result.returncode, result.stdout)
            return MeshHandle(case_dir=case_dir, ok=False)

        # 2. pyfr partition (only when mpi_n > 1; single-GPU H100 skips).
        if self.mpi_n is not None and self.mpi_n > 1:
            partition_cmd = build_apptainer_exec(
                sif_path=self.sif_path,
                case_bind_source=str(case_dir.remote_path),
                command=f"pyfr partition {self.mpi_n} {_MESH_PYFRM} .",
                gpu=False,
            )
            part_result = executor.run(partition_cmd, timeout_s=900)
            if not part_result.ok:
                logger.error(
                    "pyfr partition failed (rc={}):\n{}",
                    part_result.returncode,
                    part_result.stdout,
                )
                return MeshHandle(case_dir=case_dir, ok=False)

        # 3. Derive element + DOF counts from the spec.
        n_elements: int | None = None
        n_dof: int | None = None
        if isinstance(spec, PyFRTaylorGreenSpec):
            n_elements = spec.n_elements_per_dir**3
            n_dof = n_elements * (spec.polynomial_order + 1) ** 3
        elif isinstance(spec, PyFRMeshFileSpec):
            n_elements = _count_msh_hex_elements(case_dir.host_path / _MESH_MSH)
            if n_elements is not None:
                n_dof = n_elements * (spec.polynomial_order + 1) ** 3

        # Verify the .pyfrm landed on disk (the only ground-truth post-import).
        pyfrm = case_dir.host_path / _MESH_PYFRM
        ok = pyfrm.is_file()
        if not ok:
            logger.error("pyfr import succeeded (rc=0) but {} is missing", pyfrm)
        return MeshHandle(case_dir=case_dir, ok=ok, n_elements=n_elements, n_dof=n_dof)

    # --- run seam ------------------------------------------------------------
    def run(self, case_dir: CaseDir, executor: Executor) -> ResultHandle:
        """Run `pyfr run -b <backend>` inside the SIF, long-running."""
        spec = case_dir.spec
        backend = getattr(spec, "backend", "cuda")
        if backend not in {"cuda", "hip", "openmp"}:
            raise ValueError(f"unsupported PyFR backend {backend!r}")
        gpu = backend in {"cuda", "hip"}
        command = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=str(case_dir.remote_path),
            command=f"pyfr run -b {backend} -p {_SOLVER_INI} {_MESH_PYFRM}",
            gpu=gpu,
            mpi_n=self.mpi_n,
            writable_tmpfs=True,
        )
        result = executor.run(
            command,
            long_running=True,
            session=f"pyfr-{case_dir.run_id}",
        )
        return ResultHandle(
            case_dir=case_dir,
            returncode=result.returncode,
            output_host_path=case_dir.host_path,
            solver_log=result.stdout,
        )

    # --- load seam -----------------------------------------------------------
    def load(self, result: ResultHandle) -> SolveResult:
        """Parse `out/integrate.csv` into a typed `TimeHistory` + `SolveResult`.

        PyFR's `[soln-plugin-integrate]` block writes per-step monitor values:
        `t,ke-int,enstrophy-int`. Taylor-Green dissipation rate is
        `epsilon(t) = -d(ke)/dt`; we recover it via `np.gradient`. The peak
        dissipation and its time are recorded as case scalars (the
        Brachet-canonical comparison metric).
        """
        csv_path = result.case_dir.host_path / _INTEGRATE_CSV
        if not csv_path.is_file():
            raise FileNotFoundError(
                f"PyFR integrate output missing: {csv_path}; the solve may "
                "have failed before the first monitor write — check the SIF log."
            )
        t_list: list[float] = []
        ke_list: list[float] = []
        with csv_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                t_list.append(float(row["t"]))
                ke_list.append(float(row["ke-int"]))
        if len(t_list) < 2:
            raise ValueError(
                f"PyFR integrate output has fewer than 2 samples ({len(t_list)}); "
                "cannot compute dissipation rate."
            )
        t_arr = np.asarray(t_list)
        ke_arr = np.asarray(ke_list)
        # Domain volume normalisation: the Brachet reference is the volume-averaged
        # kinetic energy. PyFR's integrate plugin emits the integral over the
        # domain; for the canonical [-pi, pi]^3 cube the volume is (2*pi)^3.
        diss = -np.gradient(ke_arr, t_arr)
        peak_idx = int(np.argmax(diss))
        return SolveResult(
            run_id=result.case_dir.run_id,
            case_name=result.case_dir.spec.name,
            cd=None,  # periodic-cube scale-resolving case has no airfoil force coefficient
            cl=None,
            iterations_to_convergence=len(t_arr),
            final_residual=float(diss[-1]),
            history=TimeHistory(
                t=tuple(t_arr.tolist()),
                monitor=tuple(diss.tolist()),
                monitor_name="dissipation_rate",
            ),
            scalars={
                "peak_dissipation": float(diss[peak_idx]),
                "peak_dissipation_t": float(t_arr[peak_idx]),
                "final_kinetic_energy": float(ke_arr[-1]),
            },
            source=str(csv_path),
        )

    # --- wall_distribution seam ----------------------------------------------
    def wall_distribution(self, result: ResultHandle, *, patch: str) -> WallDistribution:
        spec_name = result.case_dir.spec.name
        # Both PyFR cases this stage ships are periodic (TG) or use
        # internal-flow wall sampling (periodic hill — deferred to Stage 12).
        raise NotImplementedError(
            f"PyFR case {spec_name!r} has no wall to sample at patch={patch!r}. "
            "Taylor-Green is triply periodic. Periodic-hill wall extraction is "
            "deferred to Stage 12 (a `[soln-plugin-sampler]` block writing "
            "wall_sample.csv host-side)."
        )


# --- module helpers ----------------------------------------------------------
_MSH_ELEMENTS_HEADER_RE = re.compile(r"^\$Elements\s*$", re.MULTILINE)
_MSH_END_ELEMENTS_RE = re.compile(r"^\$EndElements\s*$", re.MULTILINE)
_MSH_HEX_TYPE_RE = re.compile(r"^\d+\s+5\s+", re.MULTILINE)


def _count_msh_hex_elements(msh_path: Path) -> int | None:
    """Count gmsh element-type-5 (hex8) entries in `$Elements` block.

    Returns None if the file is unreadable or has no `$Elements` block. The
    structured TG mesh we emit uses element-type 5 for the volume hex; the
    mesh-file path may use mixed element types — we count only hex.
    """
    try:
        text = msh_path.read_text(encoding="utf-8")
    except OSError:
        return None
    start = _MSH_ELEMENTS_HEADER_RE.search(text)
    end = _MSH_END_ELEMENTS_RE.search(text)
    if not start or not end:
        return None
    block = text[start.end() : end.start()]
    return len(_MSH_HEX_TYPE_RE.findall(block))
