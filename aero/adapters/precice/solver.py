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
from typing import assert_never

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
from aero.adapters.precice.analysis import TIP_UX, TIP_UY, analyse_displacement_watchpoint
from aero.adapters.precice.case import (
    CASE_ROOT_DIRNAME,
    CoupledCaseError,
    CoupledCaseSpec,
    MaterializedTree,
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
from aero.adapters.precice.manifest import render_tutorial_manifest_json
from aero.adapters.precice.watchpoint import WatchpointTrace, read_watchpoint, watchpoint_path
from aero.orchestration._base import Executor, describe_failure

DEFAULT_PRECICE_SIF_PATH = "/opt/aero/containers/precice-fsi.sif"
DEFAULT_SIF_DIR = "/opt/aero/containers"

#: blockMesh's "Mesh Information" block, verified against real v2412 output:
#:     nPoints: 42938
#:     nCells: 20969
#: NOT "cells:" -- that is checkMesh's wording, and confusing the two is how Stage 18
#: ended up publishing a pre-snap cell count in a provenance-bearing field.
_N_CELLS_RE = re.compile(r"^\s*nCells:\s*(\d+)\s*$", re.MULTILINE)

_MESH_TIMEOUT_S = 1800


class PreciceSolverError(RuntimeError):
    """A coupled preCICE run could not be prepared, meshed, executed or read."""


def _chown_tree(root: Path, *, uid: int) -> None:
    """Recursively chown `root` to `uid`:`uid`."""
    import os

    for path in (root, *root.rglob("*")):
        os.chown(path, uid, uid)


def _window_indices(t_start: float, t_end: float, *, window_size: float) -> tuple[int, int]:
    """preCICE TimeWindow indices spanning ``[t_start, t_end]``.

    preCICE logs ``TimeWindow = _timeWindows - 1``, and the watch-point's first row is
    the first COMPLETED window, so the window whose end is at time t has index
    ``round(t / dt) - 1``. Clamped at zero, and widened by nothing: the bound is inclusive
    on both ends so the analysis window's own first and last windows are both checked.
    """
    if window_size <= 0.0:
        raise PreciceSolverError(f"non-positive coupling time-window size {window_size!r}")
    first = max(round(t_start / window_size) - 1, 0)
    last = max(round(t_end / window_size) - 1, first)
    return first, last


def _assert_status_gate(status: CoupledRunResult, *, run_id: str, solver_log: str) -> None:
    """Gate K2 — refuse every run ending except the two that are reportable.

    Extracted so the solver's load path and the campaign drivers share ONE implementation.
    Before this, ``load()`` checked both endings while the Stage-19 driver checked only
    "a participant died" and never implemented the ceiling-desynchronisation half at all —
    two gates with the same name and different behaviour.

    The two admissible endings are: everyone exited cleanly, or the ceiling stopped a run in
    which EVERY participant was still alive. A run where one participant had already exited
    when the ceiling fired is a desynchronised coupling wearing a budget outcome's clothes.
    """
    if status.stopped_by == "participant-died":
        died = [o.name for o in status.outcomes if o.state == "exited-fail"]
        raise PreciceSolverError(
            f"{run_id}: the coupled run ended because a participant died"
            f"{' (' + ', '.join(died) + ')' if died else ''}. A partial coupled solve is "
            f"not reportable.\n{solver_log[-2000:]}"
        )
    if status.stopped_by == "ceiling":
        already_gone = [o.name for o in status.outcomes if o.state != "killed"]
        if already_gone:
            raise PreciceSolverError(
                f"{run_id}: the ceiling stopped the run, but "
                f"{', '.join(already_gone)} had already exited — the participants were "
                "no longer coupled. Gate K2 admits a ceiling stop only with every "
                "participant still running; this record is not reportable."
            )


def _assert_coupling_converged_over(
    reports: tuple[CouplingIterationReport, ...], *, first_window: int, last_window: int
) -> tuple[CouplingIterationReport, ...]:
    """Gate K1 — every coupling window inside the analysis window converged.

    Returns the WINDOW-SCOPED reports, because the caller also derives
    ``coupling_mean_iterations`` / ``coupling_max_iterations`` from them; a ``-> None``
    extraction would silently revert those two scalars to whole-run values.

    K1 applies to the ANALYSIS WINDOW, not the whole run. Upstream documents that the first
    time windows need many coupling iterations, so failing a run for a capped window at
    t = 0.01 s would be a spurious NO-GO about the start-up transient — and asserting over
    everything is how ``CouplingIterationReport.within()`` became dead code.
    """
    scoped = tuple(r.within(first_window=first_window, last_window=last_window) for r in reports)
    for report in scoped:
        assert_coupling_converged(report)
    return scoped


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
        self._trees: dict[str, MaterializedTree] = {}
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
        return case_dir.host_path / CASE_ROOT_DIRNAME

    def _remote_case_root(self, case_dir: CaseDir) -> str:
        return f"{case_dir.remote_path}/{CASE_ROOT_DIRNAME}"

    def config_for(self, case_dir: CaseDir) -> PreciceConfig:
        """The parsed configuration this run will use (populated by `prepare`)."""
        try:
            return self._configs[case_dir.run_id]
        except KeyError:
            spec = self._coupled_spec(case_dir.spec)
            config = read_precice_config(
                self._case_root(case_dir) / spec.case_subdir / "precice-config.xml"
            )
            self._configs[case_dir.run_id] = config
            return config

    # --- lifecycle seams -------------------------------------------------------

    def _materialize(
        self, spec: CoupledCaseSpec, root: Path
    ) -> tuple[MaterializedTree, PreciceConfig]:
        """Lay the case's bytes down under `root` and return the tree plus its config.

        A METHOD, not a free function in ``case.py``: an authored case's materializer has to
        drive the OpenFOAM and CalculiX writers, and ``launcher.py`` imports ``case.py``, so
        anything ``case.py`` imports at module level is transitively pulled into every
        launcher consumer.

        It does NOT write the manifest. ``_write_case`` owns that tail
        (`assert_config` -> chown -> manifest) because the chown must not touch
        ``aero-manifest.json``: the case belongs to the unprivileged participants, but the
        manifest is the platform's own record and stays root-owned. That ordering is pinned
        by absence in ``test_the_case_is_chowned_before_the_manifest_is_written``.
        """
        source = spec.source
        if source.kind != "tutorial":
            raise PreciceSolverError(
                f"case {spec.name!r}: authored-case materialization lands in Stage 20 "
                "Phase 3B; no writer is registered for it yet"
            )
        tree = materialize_tutorial(source, dest=root)
        tree = select_fluid_mesh(
            tree,
            variant=source.fluid_mesh_dict,
            case_dir=tree.case_dir,
            fluid_participant_dir=source.fluid_participant_dir,
        )

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
        return tree, produced

    def _render_manifest(self, tree: MaterializedTree) -> str:
        """Select the manifest schema by an exhaustive match on the source discriminator."""
        source = tree.source
        case_dir_rel = str(tree.case_dir.relative_to(tree.root))
        match source.kind:
            case "tutorial":
                return render_tutorial_manifest_json(
                    pin=source.pin,
                    case_dir_rel=case_dir_rel,
                    files=tree.files,
                    mutations=tree.mutations,
                )
            case "authored":
                raise PreciceSolverError(
                    "the authored manifest emitter lands with the authored writer "
                    "(Stage 20 Phase 3B)"
                )
            case _ as unreachable:  # pragma: no cover - mypy proves this unreachable
                assert_never(unreachable)

    def _write_case(self, case: SpecLike, host_path: Path) -> None:
        spec = self._coupled_spec(case)
        root = host_path / CASE_ROOT_DIRNAME
        tree, produced = self._materialize(spec, root)

        if self.expectation is not None:
            assert_config(produced, self.expectation)

        if spec.run_as_uid is not None:
            # The participants run unprivileged (see ParticipantSpec.run_as_uid), so the
            # case they write into has to belong to them. Done AFTER the manifest check,
            # so digest verification still runs against the bytes as acquired.
            _chown_tree(root, uid=spec.run_as_uid)

        (root / "aero-manifest.json").write_text(self._render_manifest(tree), encoding="utf-8")
        self._trees[Path(host_path).name] = tree
        pin = spec.tutorial_pin
        logger.info(
            "materialized {} @ {} ({} files, {} declared mutation(s))",
            spec.case_subdir,
            pin.commit[:12] if pin is not None else "authored",
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
            command=f"cd {spec.case_subdir}/{spec.fluid_participant_dir} && blockMesh",
        ).replace("apptainer exec ", "apptainer exec --no-home ", 1)

        result = executor.run(command, timeout_s=_MESH_TIMEOUT_S)
        polymesh = (
            self._case_root(case_dir)
            / spec.case_subdir
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
        failure = ""
        if not ok:
            failure = describe_failure(result, what=f"fluid meshing for {case_dir.run_id}")
            if result.returncode == 0 and not polymesh.is_file():
                failure = (
                    f"fluid meshing for {case_dir.run_id} exited 0 but wrote no "
                    f"constant/polyMesh/points under {spec.fluid_participant_dir}"
                )
            logger.error("{}", failure)
        return MeshHandle(case_dir=case_dir, ok=ok, n_elements=n_cells, n_dof=None, failure=failure)

    def run(self, case_dir: CaseDir, executor: Executor) -> ResultHandle:
        """Launch every participant concurrently under the supervisor script."""
        spec = self._coupled_spec(case_dir.spec)
        # Bind the tutorial ROOT, not the case directory: upstream's run.sh scripts source
        # ../../tools/log.sh and call ../../tools/run-openfoam.sh, which resolve OUTSIDE
        # the case directory. Binding only the case would leave those paths pointing at a
        # /tools that does not exist inside the container.
        plan = CoupledLaunchPlan(
            case_root_remote=self._remote_case_root(case_dir),
            participants=tuple(
                p.model_copy(update={"workdir": f"{spec.case_subdir}/{p.workdir}"})
                for p in spec.participants
            ),
            sif_paths={p.sif: f"{self.sif_dir}/{p.sif}" for p in spec.participants},
            wall_clock_ceiling_s=spec.wall_clock_ceiling_s,
            # preCICE writes precice-run/ beside the config, one level in from the root.
            exchange_dir=spec.case_subdir,
        )
        case_root_host = self._case_root(case_dir)
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
        workdir = f"{spec.case_subdir}/{spec.participant(participant).workdir}"
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
        _assert_status_gate(status, run_id=result.case_dir.run_id, solver_log=result.solver_log)

        trace = self.watchpoint(result)
        uy = trace.signal("Displacement1")
        t = uy.t_array
        analysis = analyse_displacement_watchpoint(
            trace,
            discard_s=spec.analysis_discard_s,
            min_cycles=spec.analysis_min_cycles,
        )

        window_size = self.config_for(result.case_dir).coupling_scheme.time_window_size
        first_window, last_window = _window_indices(
            analysis.t_start, analysis.t_end, window_size=window_size
        )
        reports = _assert_coupling_converged_over(
            self.coupling_report(result), first_window=first_window, last_window=last_window
        )
        tip_uy = analysis.of(TIP_UY)
        tip_ux = analysis.of(TIP_UX)

        scalars: dict[str, float] = {
            # Gated quantities (ADR-036 D1-D5), over the DERIVED analysis window.
            "tip_uy_amplitude": tip_uy.amplitude,
            "tip_uy_frequency": analysis.fundamental_frequency,
            "tip_ux_amplitude": tip_ux.amplitude,
            "tip_ux_mean": tip_ux.mean,
            "tip_ux_frequency": tip_ux.frequency,
            # Diagnostics (X) — reported, never gated.
            "tip_uy_mean": tip_uy.mean,
            "analysis_t_start": analysis.t_start,
            "analysis_t_end": analysis.t_end,
            "analysis_n_settled_cycles": float(analysis.n_settled_cycles),
            "analysis_cumulative_mean_drift": analysis.cumulative_mean_drift,
            "analysis_cumulative_amplitude_drift": analysis.cumulative_amplitude_drift,
            "coupling_first_window": float(first_window),
            "coupling_last_window": float(last_window),
            "analysis_mean_drift": analysis.mean_drift,
            "analysis_amplitude_drift": analysis.amplitude_drift,
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
