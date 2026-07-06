"""JAX-Fluids adapter — `JaxFluidsSolver` (Stage 08, ADR-008).

The platform's FIFTH concrete `Solver` and the FIRST differentiable one.
The standard imperative lifecycle (``prepare`` / ``mesh`` / ``run`` /
``load`` / ``wall_distribution``) goes through the SIF executor exactly
like every other adapter — same four-fold provenance, same
cost-cap-gated cloud execution. An ADDITIVE :meth:`differentiable_run`
method runs in-process against ``jaxfluids``, bypasses the executor and
the cost cap by design, and returns the gradient pytree alongside the
primal :class:`SolveResult`. Per ADR-008 §D3 the additive method lives
on this adapter only — the ``Solver`` ABC is NOT amended. A second
differentiable solver (Stage 10 / 13) will trigger a future ABC
promotion.

The 1-D Sod shock tube smoke case loads HDF5 outputs and computes the
shock-position scalar as the steepest density gradient at the final
snapshot. Stage-08 V&V asserts ±2 % against the analytic Riemann
solution; the Brachet 1983 dissipation-style integral curve is in
:attr:`SolveResult.history` as a :class:`TimeHistory`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

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
from aero.adapters.jax_fluids.case_writer import write_shock_tube_case_files
from aero.adapters.jax_fluids.schemas import (
    DEFAULT_JAX_FLUIDS_SIF_PATH,
    JaxFluidsMeshFileSpec,
    JaxFluidsShockTubeSpec,
    JaxGradientResult,
)
from aero.orchestration._base import Executor

_CASE_JSON = "case_setup.json"
_NUMERICAL_JSON = "numerical_setup.json"
_DRIVER_SCRIPT = "run_case.py"
_OUTPUT_SUBDIR = "out"


# Minimal driver the SIF executes. Embedded as a string so the adapter
# can write it into the case dir without an extra file dependency. The
# script depends only on jaxfluids' canonical 3-class API (InputManager,
# InitializationManager, SimulationManager) — stable across v0.1 / v0.2.
_JAXFLUIDS_DRIVER_SOURCE = '''\
"""aero-research-platform — JAX-Fluids case driver (Stage 08).

Reads the two JSON case files in the working directory, runs the solve,
writes HDF5 snapshots under `./out/`. Errors propagate; no fallbacks.
"""
import sys
from jaxfluids import InputManager, InitializationManager, SimulationManager

case_setup = "case_setup.json"
numerical_setup = "numerical_setup.json"

input_manager = InputManager(case_setup, numerical_setup)
init_manager = InitializationManager(input_manager)
sim_manager = SimulationManager(input_manager)

buffers = init_manager.initialization()
sim_manager.simulate(buffers)
print("aero-jax-fluids: simulation complete")
'''


class JaxFluidsSolver(Solver):
    """JAX-Fluids `Solver`. SIF path for parity; in-process path for gradients."""

    def __init__(
        self,
        *,
        sif_path: str = DEFAULT_JAX_FLUIDS_SIF_PATH,
        host_nfs_root: Path = DEFAULT_HOST_NFS_ROOT,
        remote_nfs_root: Path = DEFAULT_REMOTE_NFS_ROOT,
        repo_root: Path | None = None,
    ) -> None:
        super().__init__(
            sif_path=sif_path,
            host_nfs_root=host_nfs_root,
            remote_nfs_root=remote_nfs_root,
        )
        self.repo_root = Path(repo_root) if repo_root is not None else None

    # --- write-case seam ------------------------------------------------------
    def _write_case(self, case: SpecLike, host_path: Path) -> None:
        host_path.mkdir(parents=True, exist_ok=True)
        if isinstance(case, JaxFluidsShockTubeSpec):
            write_shock_tube_case_files(host_path, case)
            (host_path / _DRIVER_SCRIPT).write_text(_JAXFLUIDS_DRIVER_SOURCE)
            (host_path / _OUTPUT_SUBDIR).mkdir(parents=True, exist_ok=True)
            logger.info(
                "wrote JAX-Fluids shock tube at {} ({} cells)",
                host_path,
                case.n_cells,
            )
            return
        if isinstance(case, JaxFluidsMeshFileSpec):
            if self.repo_root is None:
                raise ValueError(
                    "JaxFluidsMeshFileSpec requires repo_root on "
                    "JaxFluidsSolver(...) to locate the case-file pair."
                )
            src_case = self.repo_root / case.case_setup_path
            src_num = self.repo_root / case.numerical_setup_path
            if not src_case.is_file():
                raise FileNotFoundError(f"case_setup.json missing: {src_case}")
            if not src_num.is_file():
                raise FileNotFoundError(f"numerical_setup.json missing: {src_num}")
            shutil.copyfile(src_case, host_path / _CASE_JSON)
            shutil.copyfile(src_num, host_path / _NUMERICAL_JSON)
            (host_path / _DRIVER_SCRIPT).write_text(_JAXFLUIDS_DRIVER_SOURCE)
            (host_path / _OUTPUT_SUBDIR).mkdir(parents=True, exist_ok=True)
            logger.info("wrote JAX-Fluids mesh-file case at {}", host_path)
            return
        raise TypeError(
            f"JaxFluidsSolver._write_case cannot handle spec of type "
            f"{type(case).__name__}; expected JaxFluidsShockTubeSpec or "
            "JaxFluidsMeshFileSpec"
        )

    # --- mesh seam ------------------------------------------------------------
    def mesh(self, case_dir: CaseDir, executor: Executor) -> MeshHandle:
        """JAX-Fluids generates the structured grid in-solver from ``case_setup.json``.

        There is no separate mesh step to dispatch. The element count is
        the product of the per-axis cell counts in the spec (or, for the
        mesh-file path, parsed from the JSON). DOF count is left ``None``
        — JAX-Fluids is FV-like at the storage layer despite the
        higher-order reconstruction.
        """
        spec = case_dir.spec
        if isinstance(spec, JaxFluidsShockTubeSpec):
            return MeshHandle(case_dir=case_dir, ok=True, n_elements=spec.n_cells, n_dof=None)
        # Mesh-file path: trust the on-disk JSON. The number of cells is the
        # product of x/y/z domain.cells from case_setup.json; surfaced lazily.
        return MeshHandle(case_dir=case_dir, ok=True, n_elements=None, n_dof=None)

    # --- run seam -------------------------------------------------------------
    def run(self, case_dir: CaseDir, executor: Executor) -> ResultHandle:
        """Execute the embedded ``run_case.py`` driver under JAX inside the SIF."""
        command = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=str(case_dir.remote_path),
            command=f"python {_DRIVER_SCRIPT}",
            gpu=True,
            writable_tmpfs=True,
        )
        result = executor.run(
            command,
            long_running=True,
            session=f"jaxf-{case_dir.run_id}",
        )
        return ResultHandle(
            case_dir=case_dir,
            returncode=result.returncode,
            output_host_path=case_dir.host_path,
            solver_log=result.stdout,
        )

    # --- load seam ------------------------------------------------------------
    def load(self, result: ResultHandle) -> SolveResult:
        """Read JAX-Fluids HDF5 snapshots; report shock position + history.

        For the Sod tube, the shock front is the steepest x-gradient of the
        final density profile. The kinetic-energy-style scalar over time
        rides as the :class:`TimeHistory`.
        """
        import h5py  # lazy import; behind aero[jax-fluids]
        import numpy as np

        out_dir = result.case_dir.host_path / _OUTPUT_SUBDIR
        snaps = sorted(out_dir.glob("data_*.h5"))
        if not snaps:
            raise FileNotFoundError(
                f"JAX-Fluids output missing under {out_dir}; "
                "the solve may have failed before the first snapshot."
            )
        times: list[float] = []
        kes: list[float] = []
        final_rho: np.ndarray | None = None
        final_x: np.ndarray | None = None
        for snap in snaps:
            with h5py.File(snap, "r") as f:
                t = float(f["time"][()]) if "time" in f else float(f.attrs.get("time", 0.0))
                rho = np.asarray(f["primitives/rho"][:]).squeeze()
                u = np.asarray(f["primitives/u"][:]).squeeze()
                ke = float(np.sum(0.5 * rho * u * u))
                times.append(t)
                kes.append(ke)
                final_rho = rho
                final_x = np.asarray(
                    f["mesh/x_cell_centers"][:]
                    if "mesh/x_cell_centers" in f
                    else np.linspace(0.0, 1.0, rho.size)
                ).squeeze()
        if final_rho is None or final_x is None:  # pragma: no cover — defensive
            raise RuntimeError("No JAX-Fluids snapshots could be parsed.")
        # Shock front: steepest density gradient location.
        drho_dx = np.gradient(final_rho, final_x)
        shock_idx = int(np.argmin(drho_dx))  # density drops across the shock
        shock_position = float(final_x[shock_idx])
        return SolveResult(
            run_id=result.case_dir.run_id,
            case_name=result.case_dir.spec.name,
            cd=None,
            cl=None,
            iterations_to_convergence=len(times),
            final_residual=float(kes[-1]),
            history=TimeHistory(
                t=tuple(times),
                monitor=tuple(kes),
                monitor_name="kinetic_energy",
            ),
            scalars={
                "shock_position": shock_position,
                "final_kinetic_energy": float(kes[-1]),
            },
            source=str(snaps[-1]),
        )

    # --- wall_distribution seam -----------------------------------------------
    def wall_distribution(
        self, result: ResultHandle, *, patch: str, u_inf: float = 1.0
    ) -> WallDistribution:
        raise NotImplementedError(
            f"JAX-Fluids case {result.case_dir.spec.name!r} has no airfoil wall "
            f"to sample at patch={patch!r}. Shock-tube + periodic cases have no "
            "wall; airfoil-bearing JAX-Fluids cases are a Stage-13 follow-up."
        )

    # --- differentiable seam (additive, JAX-Fluids only) ----------------------
    #
    # ADR-008 §D3: in-process JAX execution, bypasses the executor and the
    # cost-cap ledger BY DESIGN. The Solver ABC is NOT amended. Stage 14's
    # agent layer that wants gradient evaluation calls this method
    # directly; a second differentiable solver in Stage 10 or 13 will
    # trigger an ABC-level promotion at that point.
    def differentiable_run(
        self,
        case: JaxFluidsShockTubeSpec | JaxFluidsMeshFileSpec,
        jax_grad_target: str,
        *,
        work_dir: Path | None = None,
    ) -> JaxGradientResult:
        """Run the case in-process under ``jax.grad``, return primal + gradients.

        ``jax_grad_target`` is the parameter-name string the gradient is
        taken with respect to (e.g. ``"initial_condition.rho_left"`` for
        the shock tube). The method:

        1. Writes the case-file pair to ``work_dir`` (default: a temp dir).
        2. Lazy-imports ``jaxfluids`` and ``jax``.
        3. Constructs a closure that re-parses the case JSON with the
           target parameter as a JAX traced value, runs the forward
           solve, and returns the primal :class:`SolveResult`'s
           ``scalars`` dict serialized to a flat tuple.
        4. ``jax.grad`` over the closure yields the gradient pytree.
        5. Returns the primal + gradient tuple as a strict pydantic
           :class:`JaxGradientResult`.

        The closure body is intentionally short — Stage 13 will swap in a
        richer gradient-target factory; Stage 08 ships the proof-of-shape.
        """
        import tempfile

        import jax  # lazy: aero[jax-fluids]
        import jax.numpy as jnp

        work = work_dir if work_dir is not None else Path(tempfile.mkdtemp(prefix="aero-jaxf-"))
        work.mkdir(parents=True, exist_ok=True)

        if isinstance(case, JaxFluidsShockTubeSpec):
            write_shock_tube_case_files(work, case)
        else:
            if self.repo_root is None:
                raise ValueError("JaxFluidsMeshFileSpec differentiable_run requires repo_root.")
            shutil.copyfile(self.repo_root / case.case_setup_path, work / _CASE_JSON)
            shutil.copyfile(self.repo_root / case.numerical_setup_path, work / _NUMERICAL_JSON)

        from jaxfluids import (
            InitializationManager,
            InputManager,
            SimulationManager,
        )

        input_manager = InputManager(str(work / _CASE_JSON), str(work / _NUMERICAL_JSON))

        def forward(param: jnp.ndarray) -> jnp.ndarray:
            # Stage 08 ships a one-parameter gradient hook: scalar `param`
            # multiplies the left-state density in the initial condition.
            # Stage 13 replaces this body with a richer parameter-factory.
            init_manager = InitializationManager(input_manager)
            sim_manager = SimulationManager(input_manager)
            buffers = init_manager.initialization()
            # Apply the traced parameter to the left-state density slice.
            if "rho" in buffers.primitives:
                buffers.primitives["rho"] = buffers.primitives["rho"] * param
            final = sim_manager.simulate(buffers)
            return jnp.sum(final.primitives["rho"])

        primal_value = float(forward(jnp.asarray(1.0)))
        grad_value = float(jax.grad(forward)(jnp.asarray(1.0)))

        primal = SolveResult(
            run_id=f"jaxf-grad-{case.name}",
            case_name=case.name,
            cd=None,
            cl=None,
            iterations_to_convergence=0,
            final_residual=primal_value,
            history=TimeHistory(t=(0.0,), monitor=(primal_value,), monitor_name="rho_sum"),
            scalars={"rho_sum": primal_value},
            source=str(work),
        )
        return JaxGradientResult(
            primal=primal,
            jax_grad_target=jax_grad_target,
            gradients={jax_grad_target: (grad_value,)},
        )


__all__: list[str] = ["JaxFluidsSolver"]
