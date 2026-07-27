"""``PreciceCoupledSolver`` — a partitioned FSI run behind the platform's solver contract.

The ``Solver`` ABC is **not** amended for this adapter. A coupled run does fit
``prepare -> mesh -> run -> load`` once the ``CaseDir`` is taken to be the tutorial root
and the participants are directories inside it:

* ``prepare`` materializes the digest-verified pinned tutorial, applies the two declared
  mutations, and asserts the preCICE configuration against the pre-registered
  expectation;
* ``mesh`` runs ``blockMesh`` for the fluid participant (the Nutils solid meshes itself
  from ``solid.geo`` at start-up);
* ``run`` launches both participants concurrently under the supervisor;
* ``load`` reads the flag-tip watch-point into a ``TimeHistory`` — and asserts the
  coupling converged before returning anything.

Two Stage-07 protocol promotions are what make this fit without touching the ABC:
``SolveResult.cd``/``.cl`` are ``float | None``, and ``scalars`` exists for
case-specific outputs. That is the same reasoning ADR-008 used to add JAX-Fluids'
differentiable path as a sibling rather than widening the base class.

``wall_distribution`` raises: a partitioned FSI run has no single wall Cf/Cp
distribution to return, and returning an empty one would be a silent fallback.
"""

from __future__ import annotations

import re
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
from aero.adapters.precice.case import (
    CoupledCaseError,
    CoupledCaseSpec,
    TutorialTree,
    materialize_tutorial,
    record_max_time_mutation,
    select_fluid_mesh,
)
from aero.adapters.precice.config import (
    PreciceConfig,
    PreciceConfigExpectation,
    assert_config,
    read_precice_config,
    rewrite_max_time,
)
from aero.adapters.precice.launcher import (
    CoupledLaunchPlan,
    CoupledRunResult,
    launch_coupled,
    read_coupled_status,
)
from aero.adapters.precice.logs import (
    CouplingIterationReport,
    assert_coupling_converged,
    find_iterations_logs,
    read_iterations_log,
)
from aero.adapters.precice.watchpoint import WatchpointTrace, read_watchpoint, watchpoint_path
from aero.orchestration._base import Executor

DEFAULT_PRECICE_SIF_PATH = "/opt/aero/containers/precice-fsi.sif"
DEFAULT_SIF_DIR = "/opt/aero/containers"

#: `blockMesh` prints this once the mesh is written.
_N_CELLS_RE = re.compile(r"^\s*cells:\s*(\d+)\s*$", re.MULTILINE)

_MESH_TIMEOUT_S = 1800


class PreciceSolverError(RuntimeError):
    """A coupled preCICE run could not be prepared, meshed, executed or read."""


class PreciceCoupledSolver(Solver):
    """Drives a two-participant preCICE case through the platform's solver lifecycle."""

    def __init__(
        self,
        *,
        sif_path: str = DEFAULT_PRECICE_SIF_PATH,
        expectation: PreciceConfigExpectation | None = None,
        host_nfs_root: Path = DEFAULT_HOST_NFS_ROOT,
        remote_nfs_root: Path = DEFAULT_REMOTE_NFS_ROOT,
        sif_dir: str = DEFAULT_SIF_DIR,
    ) -> None:
        super().__init__(
            sif_path=sif_path, host_nfs_root=host_nfs_root, remote_nfs_root=remote_nfs_root
        )
        self.expectation = expectation
        self.sif_dir = sif_dir
        self._trees: dict[str, TutorialTree] = {}
        self._configs: dict[str, PreciceConfig] = {}

    # --- helpers ---------------------------------------------------------------

    @staticmethod
    def _coupled_spec(case: SpecLike) -> CoupledCaseSpec:
        if not isinstance(case, CoupledCaseSpec):
            raise PreciceSolverError(
                f"PreciceCoupledSolver drives CoupledCaseSpec only, got {type(case).__name__}"
            )
        return case

    def _case_root(self, case_dir: CaseDir) -> Path:
        """The materialized tutorial root inside the run directory."""
        return case_dir.host_path / "tutorial"

    def _remote_case_root(self, case_dir: CaseDir) -> str:
        return f"{case_dir.remote_path}/tutorial"

    def config_for(self, case_dir: CaseDir) -> PreciceConfig:
        """The parsed configuration this run will use (populated by `prepare`)."""
        try:
            return self._configs[case_dir.run_id]
        except KeyError:
            spec = self._coupled_spec(case_dir.spec)
            config = read_precice_config(
                self._case_root(case_dir) / spec.tutorial_case / "precice-config.xml"
            )
            self._configs[case_dir.run_id] = config
            return config

    # --- lifecycle seams -------------------------------------------------------

    def _write_case(self, case: SpecLike, host_path: Path) -> None:
        spec = self._coupled_spec(case)
        root = host_path / "tutorial"
        tree = materialize_tutorial(
            spec.pin,
            archive=spec.archive_path,
            dest=root,
            tutorial_case=spec.tutorial_case,
        )
        tree = select_fluid_mesh(tree, variant=spec.fluid_mesh_dict, case_dir=tree.case_dir)

        config_path = tree.case_dir / "precice-config.xml"
        before = read_precice_config(config_path)
        produced = rewrite_max_time(config_path, config_path, max_time=spec.max_time)
        tree = record_max_time_mutation(
            tree,
            path=config_path,
            before_sha256=before.source_sha256,
            after_sha256=produced.source_sha256,
            max_time=spec.max_time,
        )

        if self.expectation is not None:
            assert_config(produced, self.expectation)

        tree.write_manifest(root / "aero-manifest.json")
        self._trees[Path(host_path).name] = tree
        logger.info(
            "materialized {} @ {} ({} files, {} declared mutation(s))",
            spec.tutorial_case,
            spec.pin.commit[:12],
            len(tree.files),
            len(tree.mutations),
        )

    def mesh(self, case_dir: CaseDir, executor: Executor) -> MeshHandle:
        """Run ``blockMesh`` for the fluid participant.

        The Nutils solid builds its own mesh from ``solid.geo`` when it starts, so there
        is nothing to do for it here — and nothing to report: ``n_elements`` is the fluid
        cell count, which is the number that identifies the rung.
        """
        spec = self._coupled_spec(case_dir.spec)
        remote_root = self._remote_case_root(case_dir)
        command = build_apptainer_exec(
            sif_path=self.sif_path,
            case_bind_source=remote_root,
            command=f"cd {spec.tutorial_case}/{spec.fluid_participant_dir} && blockMesh",
        ).replace("apptainer exec ", "apptainer exec --no-home ", 1)

        result = executor.run(command, timeout_s=_MESH_TIMEOUT_S)
        polymesh = (
            self._case_root(case_dir)
            / spec.tutorial_case
            / spec.fluid_participant_dir
            / "constant"
            / "polyMesh"
            / "points"
        )
        ok = result.returncode == 0 and polymesh.is_file()
        match = _N_CELLS_RE.search(result.stdout)
        n_cells = int(match.group(1)) if match else None
        if ok and n_cells is None:
            raise PreciceSolverError(
                f"{case_dir.run_id}: blockMesh succeeded but its cell count could not be "
                "parsed — refusing to report a mesh whose size is unknown, since the "
                "cell count is what identifies the rung in the provenance record"
            )
        if not ok:
            logger.error("blockMesh failed for {}:\n{}", case_dir.run_id, result.stdout[-2000:])
        return MeshHandle(case_dir=case_dir, ok=ok, n_elements=n_cells, n_dof=None)

    def run(self, case_dir: CaseDir, executor: Executor) -> ResultHandle:
        """Launch every participant concurrently under the supervisor script."""
        spec = self._coupled_spec(case_dir.spec)
        plan = CoupledLaunchPlan(
            case_root_remote=f"{self._remote_case_root(case_dir)}/{spec.tutorial_case}",
            participants=spec.participants,
            sif_paths={p.sif: f"{self.sif_dir}/{p.sif}" for p in spec.participants},
            wall_clock_ceiling_s=spec.wall_clock_ceiling_s,
        )
        case_root_host = self._case_root(case_dir) / spec.tutorial_case
        outcome = launch_coupled(
            plan, executor, run_id=case_dir.run_id, case_root_host=case_root_host
        )
        logger.info(
            "coupled run {} stopped_by={} after {:.0f}s",
            case_dir.run_id,
            outcome.stopped_by,
            outcome.wall_clock_s,
        )
        return ResultHandle(
            case_dir=case_dir,
            returncode=outcome.executor_returncode,
            output_host_path=case_root_host,
            solver_log="\n\n".join(
                f"===== {o.name} ({o.state}, rc={o.returncode}) =====\n{o.log_tail}"
                for o in outcome.outcomes
            ),
        )

    def coupled_status(self, result: ResultHandle) -> CoupledRunResult:
        """The supervisor's recorded verdict for a finished run."""
        return read_coupled_status(
            result.output_host_path / "coupled-status.json",
            case_root_host=result.output_host_path,
            executor_returncode=result.returncode,
        )

    def watchpoint(
        self, result: ResultHandle, *, participant: str = "Solid", name: str = "Flap-Tip"
    ) -> WatchpointTrace:
        """Read a watch-point, verifying its header against the configuration (gate C4)."""
        spec = self._coupled_spec(result.case_dir.spec)
        config = self.config_for(result.case_dir)
        workdir = spec.participant(participant).workdir
        path = watchpoint_path(result.output_host_path, workdir, participant, name)
        return read_watchpoint(
            path,
            participant=participant,
            watch_point=name,
            expected_columns=config.watchpoint_columns(participant, name),
        )

    def coupling_report(self, result: ResultHandle) -> tuple[CouplingIterationReport, ...]:
        """Per-participant coupling iteration reports."""
        config = self.config_for(result.case_dir)
        cap = config.coupling_scheme.max_iterations
        if cap is None:
            raise PreciceSolverError(
                f"{result.case_dir.run_id}: the coupling scheme declares no max-iterations, "
                "so convergence cannot be judged — an implicit scheme must bound its "
                "sub-iterations"
            )
        return tuple(
            read_iterations_log(path, participant=participant, max_iterations_configured=cap)
            for participant, path in sorted(find_iterations_logs(result.output_host_path).items())
        )

    def load(self, result: ResultHandle) -> SolveResult:
        """Parse the coupled run into a `SolveResult` carrying the flag-tip history.

        The coupling-convergence gate (ADR-036 K1) is enforced HERE, not in the V&V case,
        so that no path to a number can bypass it — the same placement the moving-mesh
        adapter uses for its periodic-steady-state check.
        """
        spec = self._coupled_spec(result.case_dir.spec)
        status = self.coupled_status(result)
        if status.stopped_by == "participant-died":
            died = [o.name for o in status.outcomes if o.state == "exited-fail"]
            raise PreciceSolverError(
                f"{result.case_dir.run_id}: the coupled run ended because a participant died"
                f"{' (' + ', '.join(died) + ')' if died else ''}. A partial coupled solve is "
                f"not reportable.\n{result.solver_log[-2000:]}"
            )

        reports = self.coupling_report(result)
        for report in reports:
            assert_coupling_converged(report)

        trace = self.watchpoint(result)
        uy = trace.signal("Displacement1")
        ux = trace.signal("Displacement0")
        t = uy.t_array

        scalars: dict[str, float] = {
            "tip_uy_last": float(uy.y_array[-1]),
            "tip_ux_last": float(ux.y_array[-1]),
            "t_end": float(t[-1]),
            "n_windows": float(trace.n_rows),
            "wall_clock_s": status.wall_clock_s,
            "stopped_by_ceiling": 1.0 if status.hit_ceiling else 0.0,
            "coupling_mean_iterations": float(np.mean([r.mean_iterations for r in reports])),
            "coupling_max_iterations": float(max(r.max_observed_iterations for r in reports)),
            "max_iterations_configured": float(reports[0].max_iterations_configured),
            "max_time_configured": spec.max_time,
        }

        return SolveResult(
            run_id=result.case_dir.run_id,
            case_name=spec.name,
            cd=None,
            cl=None,
            cd_pressure=None,
            cd_viscous=None,
            iterations_to_convergence=trace.n_rows,
            final_residual=0.0,
            history=TimeHistory(
                kind="time",
                t=tuple(float(v) for v in t),
                monitor=tuple(float(v) for v in uy.y_array),
                monitor_name="flap_tip_uy",
            ),
            scalars=scalars,
            source=str(trace.path),
        )

    def wall_distribution(
        self, result: ResultHandle, *, patch: str, u_inf: float = 1.0
    ) -> WallDistribution:
        raise NotImplementedError(
            "a partitioned FSI run has no single wall Cf/Cp distribution to return — the "
            "wall is shared between two solvers and moves. Use "
            "PreciceCoupledSolver.watchpoint(result) for the coupled interface quantities."
        )


__all__ = [
    "DEFAULT_PRECICE_SIF_PATH",
    "CoupledCaseError",
    "PreciceCoupledSolver",
    "PreciceSolverError",
]
