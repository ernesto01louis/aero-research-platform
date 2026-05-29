"""NekRS adapter — `NekRSSolver` satisfying the Stage-07 `Solver` ABC.

The lifecycle:

1. `prepare`  — base-class template method; calls `_write_case` to drop
                `<case>.box`, `<case>.par`, `<case>.udf` onto NFS.
2. `mesh`     — runs `genbox <case>.box` then `genmap <case>` inside the
                SIF to produce `<case>.re2` and `<case>.ma2`. Validates the
                `.re2` lands on disk; counts elements from the spec.
3. `run`      — runs `nekrs --setup <case> --backend CUDA --device-id 0`
                inside the SIF with `--nv` and `mpi_n` (defaults to 1).
                Long-running.
4. `load`     — parses the solver log (or `out/integrate.log` if the udf
                wrote one) for `gradKE:` lines into `TimeHistory`. Returns
                a `SolveResult` with peak dissipation in `.scalars`.
5. `wall_distribution` — raises `NotImplementedError` for periodic TG;
                          periodic-hill follow-up tracked for Stage 12.
"""

from __future__ import annotations

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
from aero.adapters._meshing.nekmesh_wrapper import write_taylor_green_box
from aero.adapters.nekrs.case_writer import (
    write_taylor_green_par,
    write_taylor_green_udf,
)
from aero.adapters.nekrs.schemas import (
    DEFAULT_NEKRS_SIF_PATH,
    NekRSCaseDirSpec,
    NekRSTaylorGreenSpec,
)
from aero.orchestration._base import Executor

# Log lines emitted by the .udf's UDF_ExecuteStep, e.g.
#   gradKE: t=2.500000e-01 tstep=500 ke=1.234567890e-01
_GRADKE_RE = re.compile(r"gradKE:\s*t=([0-9eE+\-.]+)\s+tstep=\d+\s+ke=([0-9eE+\-.]+)")


class NekRSSolver(Solver):
    """The NekRS `Solver` — Stage 07's fourth concrete adapter."""

    def __init__(
        self,
        *,
        sif_path: str = DEFAULT_NEKRS_SIF_PATH,
        host_nfs_root: Path = DEFAULT_HOST_NFS_ROOT,
        remote_nfs_root: Path = DEFAULT_REMOTE_NFS_ROOT,
        repo_root: Path | None = None,
        mpi_n: int = 1,
    ) -> None:
        super().__init__(
            sif_path=sif_path,
            host_nfs_root=host_nfs_root,
            remote_nfs_root=remote_nfs_root,
        )
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.mpi_n = max(1, int(mpi_n))  # NekRS always launches via mpirun

    # --- write-case seam ------------------------------------------------------
    def _write_case(self, case: SpecLike, host_path: Path) -> None:
        host_path.mkdir(parents=True, exist_ok=True)
        if isinstance(case, NekRSTaylorGreenSpec):
            case_name = case.case_name
            n_hex = write_taylor_green_box(
                host_path / f"{case_name}.box",
                case_name=case_name,
                n_elements_per_dir=case.n_elements_per_dir,
            )
            write_taylor_green_par(host_path / f"{case_name}.par", case)
            write_taylor_green_udf(host_path / f"{case_name}.udf", case)
            logger.info(
                "wrote NekRS Taylor-Green case at {} ({} hex elements, N={})",
                host_path,
                n_hex,
                case.polynomial_order,
            )
            return
        if isinstance(case, NekRSCaseDirSpec):
            if self.repo_root is None:
                raise ValueError(
                    "NekRSCaseDirSpec requires repo_root on NekRSSolver(...) "
                    "to locate the DVC-tracked case-asset directory."
                )
            src = self.repo_root / case.case_dir
            if not src.is_dir():
                raise FileNotFoundError(
                    f"NekRS case asset directory missing: {src} — did you `dvc pull`?"
                )
            for entry in src.iterdir():
                if entry.is_file():
                    shutil.copy2(entry, host_path / entry.name)
            logger.info("wrote NekRS case from {} into {}", src, host_path)
            return
        raise TypeError(
            f"NekRSSolver._write_case cannot handle spec of type {type(case).__name__}; "
            "expected NekRSTaylorGreenSpec or NekRSCaseDirSpec"
        )

    # --- mesh seam -----------------------------------------------------------
    def mesh(self, case_dir: CaseDir, executor: Executor) -> MeshHandle:
        """Run `genbox` then `genmap` inside the SIF to build the `.re2`/`.ma2`.

        For NekRSCaseDirSpec the `.re2` is already in the case dir — we
        only need to verify it exists and (optionally) re-run `genmap` to
        match the current mpi_n.
        """
        spec = case_dir.spec
        case_name = getattr(spec, "case_name", "taylorGreen")
        re2 = case_dir.host_path / f"{case_name}.re2"

        if isinstance(spec, NekRSTaylorGreenSpec):
            # Pipe stdin to genbox: it asks for the .box file name + nothing else.
            genbox_cmd = build_apptainer_exec(
                sif_path=self.sif_path,
                case_bind_source=str(case_dir.remote_path),
                command=f"sh -c 'echo {case_name}.box | genbox'",
                gpu=False,
            )
            r1 = executor.run(genbox_cmd, timeout_s=300)
            if not r1.ok:
                logger.error("genbox failed (rc={}):\n{}", r1.returncode, r1.stdout)
                return MeshHandle(case_dir=case_dir, ok=False)
            # genbox writes box.re2; rename to <case>.re2 (NekRS convention).
            box_re2 = case_dir.host_path / "box.re2"
            if box_re2.is_file():
                shutil.move(str(box_re2), str(re2))

        # genmap (interactive: case-name + tolerance). Echo both via stdin.
        genmap_cmd = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=str(case_dir.remote_path),
            command=f"sh -c 'printf \"{case_name}\\n0.01\\n\" | genmap'",
            gpu=False,
        )
        r2 = executor.run(genmap_cmd, timeout_s=300)
        if not r2.ok:
            logger.error("genmap failed (rc={}):\n{}", r2.returncode, r2.stdout)
            return MeshHandle(case_dir=case_dir, ok=False)

        if not re2.is_file():
            logger.error("genmap succeeded but {} is missing", re2)
            return MeshHandle(case_dir=case_dir, ok=False)

        # Element + DOF counts. For TG we derive from spec; for the case-dir
        # path we'd parse the .re2 header (deferred — Stage 12).
        n_elements: int | None = None
        n_dof: int | None = None
        if isinstance(spec, NekRSTaylorGreenSpec):
            n_elements = spec.n_elements_per_dir**3
            n_dof = n_elements * (spec.polynomial_order + 1) ** 3
        return MeshHandle(case_dir=case_dir, ok=True, n_elements=n_elements, n_dof=n_dof)

    # --- run seam ------------------------------------------------------------
    def run(self, case_dir: CaseDir, executor: Executor) -> ResultHandle:
        """Run `nekrs --setup <case> --backend <BACKEND> --device-id 0` in the SIF."""
        spec = case_dir.spec
        case_name = getattr(spec, "case_name", "taylorGreen")
        backend = getattr(spec, "backend", "CUDA")
        if backend not in {"CUDA", "HIP", "CPU"}:
            raise ValueError(f"unsupported NekRS backend {backend!r}")
        gpu = backend in {"CUDA", "HIP"}
        command = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=str(case_dir.remote_path),
            command=(f"nekrs --setup {case_name} --backend {backend} --device-id 0"),
            gpu=gpu,
            mpi_n=self.mpi_n,
            writable_tmpfs=True,
            env={"NEKRS_HOME": "/opt/nekrs", "OCCA_DIR": "/opt/nekrs/occa"},
        )
        result = executor.run(
            command,
            long_running=True,
            session=f"nekrs-{case_dir.run_id}",
        )
        return ResultHandle(
            case_dir=case_dir,
            returncode=result.returncode,
            output_host_path=case_dir.host_path,
            solver_log=result.stdout,
        )

    # --- load seam -----------------------------------------------------------
    def load(self, result: ResultHandle) -> SolveResult:
        """Parse `gradKE:` lines from the solver log into a typed TimeHistory.

        The `.udf` writes `gradKE: t=... tstep=... ke=...` each step from
        rank 0; we grep them out of the captured stdout. Dissipation is
        recovered as `-d(KE)/dt` via `np.gradient` (same pattern as PyFR).
        """
        log_text = result.solver_log
        if not log_text:
            # Try the log file at /case/<case>.log if the executor didn't
            # capture stdout in the ResultHandle (some long-running paths
            # only persist the file).
            spec_case = getattr(result.case_dir.spec, "case_name", "taylorGreen")
            log_file = result.case_dir.host_path / f"{spec_case}.log"
            if log_file.is_file():
                log_text = log_file.read_text(encoding="utf-8")
        if not log_text:
            raise FileNotFoundError(
                "NekRS solver log is empty and no .log file found — "
                "the solve may have failed before the first .udf monitor step."
            )

        t_list: list[float] = []
        ke_list: list[float] = []
        for m in _GRADKE_RE.finditer(log_text):
            t_list.append(float(m.group(1)))
            ke_list.append(float(m.group(2)))
        if len(t_list) < 2:
            raise ValueError(
                f"NekRS log has fewer than 2 gradKE samples ({len(t_list)}); "
                "cannot compute dissipation rate."
            )
        t_arr = np.asarray(t_list)
        ke_arr = np.asarray(ke_list)
        diss = -np.gradient(ke_arr, t_arr)
        peak_idx = int(np.argmax(diss))
        return SolveResult(
            run_id=result.case_dir.run_id,
            case_name=result.case_dir.spec.name,
            cd=None,
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
            source=str(result.case_dir.host_path / "solver.log"),
        )

    # --- wall_distribution seam ----------------------------------------------
    def wall_distribution(self, result: ResultHandle, *, patch: str) -> WallDistribution:
        spec_name = result.case_dir.spec.name
        raise NotImplementedError(
            f"NekRS case {spec_name!r} has no wall to sample at patch={patch!r}. "
            "Taylor-Green is triply periodic. Periodic-hill wall extraction is "
            "deferred to Stage 12."
        )
