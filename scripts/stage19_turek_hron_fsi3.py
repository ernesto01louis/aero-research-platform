"""Stage-19 campaign driver — Turek-Hron FSI3 partitioned coupling verification.

Pre-flight (I-gates) -> materialize + assert the pinned tutorial (P/C) -> blockMesh ->
coupled run under the supervisor -> periodic-steady-state analysis (S) -> displacement
bands (D) -> bundle. Clean-tree provenance: commit the code first, run without touching
the repo, write the bundle at the END only.

The pre-registered gate block is reproduced verbatim below as PREREGISTERED_GATE_BLOCK.
ADR-036 is the source of record; this is the operational copy, embedded in every bundle
the driver writes, and tests/unit/test_stage19_gate_block_sync.py asserts the two are
byte-identical.

Usage:
  # pre-flight only (I1-I4), ceiling 1 h
  python scripts/stage19_turek_hron_fsi3.py --preflight --timeout 3600

  # gated campaign (B2) and the non-gated refined diagnostic (B3)
  python scripts/stage19_turek_hron_fsi3.py --timeout 172800 --max-time 8.0
  python scripts/stage19_turek_hron_fsi3.py --timeout 172800 --max-time 8.0 \
      --mesh blockMeshDict_refined --not-gated

Long runs go through scripts/run_long.sh (unique tmux session names), never a held-open
SSH connection.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aero.adapters.precice import (  # noqa: E402
    CASE_ROOT_DIRNAME,
    CoupledCaseSpec,
    CoupledLaunchPlan,
    ParticipantSpec,
    PreciceCoupledSolver,
    launch_coupled,
    read_precice_config,
)
from aero.adapters.precice.analysis import (  # noqa: E402
    TIP_UX,
    TIP_UY,
    analyse_displacement_watchpoint,
)
from aero.adapters.precice.config import describe  # noqa: E402
from aero.adapters.precice.logs import (  # noqa: E402
    CouplingConvergenceError,
    assert_coupling_converged,
)
from aero.adapters.precice.solver import PreciceSolverError  # noqa: E402
from aero.adapters.precice.watchpoint import WatchpointError  # noqa: E402
from aero.orchestration import LocalSSHExecutor  # noqa: E402
from aero.postprocess import LimitCycleError  # noqa: E402
from aero.provenance.four_fold import (  # noqa: E402
    ProvenanceError,
    compute_provenance,
)
from aero.vv.fsi import TUREK_HRON_FSI3_EXPECTATION, TurekHronFSI3, fsi3_case_spec  # noqa: E402

_ADR = _REPO_ROOT / "docs" / "adrs" / "ADR-036-precice-fsi3-gate-preregistration.md"
_BEGIN = "<!-- GATE-BLOCK:BEGIN -->"
_END = "<!-- GATE-BLOCK:END -->"


def gate_block_from_adr(adr_path: Path = _ADR) -> str:
    """The gate block exactly as ADR-036 states it.

    Returned with a single trailing newline so it is byte-comparable with the module
    constant below, which a triple-quoted literal necessarily ends with.
    """
    text = adr_path.read_text(encoding="utf-8")
    inner = text.split(_BEGIN, 1)[1].split(_END, 1)[0]
    fenced = inner.strip()
    if not (fenced.startswith("```text") and fenced.endswith("```")):
        raise ValueError(f"{adr_path}: the gate block is not a ```text fence")
    return fenced.removeprefix("```text").removesuffix("```").strip("\n") + "\n"


PREREGISTERED_GATE_BLOCK = """\
THE PRE-REGISTERED GATE BLOCK (ADR-036 is the source of record; the campaign driver's
PREREGISTERED_GATE_BLOCK is the operational copy, embedded in every bundle; a required
unit test asserts the two are byte-identical)

P - pins and provenance (Hard Rule 8)
  P1 precice/tutorials @ cd33e2dbacc5a2f4a1202e215890f54a2ce2e79e (branch develop),
     materialized from a DVC-tracked archive and verified file-by-file against the
     git-tracked manifest tutorials_pin_manifest.csv.
  P2 preCICE v3.4.1 (libprecice3_3.4.1_noble.deb, sha256 3a36a402..be888);
     openfoam-adapter 2c3062ce941915616ac763371805c57e15e02466; pyprecice 3.4.0;
     nutils 9.2 / numpy 1.26.4 / meshio 5.3.5 / gmsh 4.15.2; OpenFOAM ESI v2412
     (image digest sha256:1ba02114..41b50); CalculiX 2.20 + calculix-adapter v2.20.1.
  P3 every gated run logs the four-fold tuple from a clean tree, with
     container_sif_sha256 = precice-fsi.sif. Evaluated by the campaign driver BEFORE the
     solve, not assumed: a dirty tree yields a "-dirty" SHA and a GATED verdict is
     refused, because the SHA would not describe what ran. A gated run spanning more than
     one SIF is structurally refused, and `gated` is DERIVED from the rung and end time
     (B2's configuration) rather than passed in, so a B3 diagnostic cannot claim the
     gated verdict.
  P4 containers/SHA256SUMS carries precice-fsi.sif and calculix-precice.sif; both are
     signed and apptainer-verify clean.
  P5 the aero[precice] pin, PINNED_PYPRECICE_VERSION and the container recipe state the
     same pyprecice version (machine-checked in required CI).

C - configuration integrity (what we run is what upstream wrote)
  C1 the materialized precice-config.xml matches TUREK_HRON_FSI3_EXPECTATION exactly:
     participants {Fluid, Solid}; scheme parallel-implicit; time-window-size 1e-3;
     max-iterations 100; convergence measures on BOTH Stress and Displacement, each of
     KIND relative-convergence-measure with limit 1e-4 (the kind is compared, not just
     the limit - 1e-4 absolute is a different problem from 1e-4 relative); acceleration
     IQN-ILS; m2n sockets; watch-point Solid/Flap-Tip at (0.6, 0.2).
  C2 the ONLY permitted modification to the upstream configuration is <max-time>, and it
     is enforced structurally: the rewritten file is re-parsed and must equal the source
     model under a max_time-only update. Loosening max-iterations, a convergence limit or
     the acceleration aborts the run.
  C3 selecting one of upstream's own blockMeshDict variants is a DECLARED mutation
     (cost/resolution among upstream-authored meshes), recorded with both digests.
  C4 the watch-point header read from the run equals the header PREDICTED from the
     configuration's mesh dimensions and use-data order. No positional column indexing.
  C5 every materialized file's sha256 is recorded in aero-manifest.json next to the case.

I - infrastructure pre-flight (all before any campaign run)
  I1 two solverdummy participants complete a serial-explicit coupling inside the SIF via
     the real supervisor launcher (proves apptainer exec, MPI_Init under the LXC, socket
     m2n, --no-home, and the launcher).
  I2 upstream 1-window cross-check against the reference-results VTUs. REPORTED, never
     gated: upstream ran OpenFOAM v2512 + deal.II and we run v2412 + Nutils.
  I3 blockMesh succeeds on the selected variant and its cell count is recorded.
  I4 a calibration run COMPLETES at least the requested 200 time windows and ends
     stopped_by == "all-exited"; its seconds-per-window and iterations-per-window are
     recorded BEFORE any budget or rung decision is taken. A run that died after a few
     windows must not yield a seconds-per-window figure, because that figure is what the
     budget decision rests on.

R - reference integrity
  R1 ref_fsi3.point matches its recorded sha256 and is identified as featflow level 4
     (ndof 304128) at dt 2.5e-4. The level is discriminated by score; dt is read from the
     series' own column, because at level 4 the tabulated dt rows agree to within the
     table's printed precision.
  R2 statistics recomputed with the platform's own estimators agree with that tabulated
     row within 3 % (ux mean, uy amplitude) and 5 % (frequency). Otherwise the campaign
     STOPS - a gate compared against a reference we do not understand is worse than no
     gate. Not "prefer whichever is closer".
  R3 the reference OF RECORD is the recomputed set (fsi3_recomputed.csv), produced by the
     same function that measures a solve; the tabulated row is reported alongside every
     gated number.

K - coupling convergence (fail-loud, enforced inside load())
  K1 ZERO time windows in the analysis window may hit max-iterations = 100, and every
     window must report Convergence == 1. A single non-converged window makes the run
     non-reportable - investigate, never relax. The window range is DERIVED from the
     S-rule's analysis window (index = round(t / time-window-size) - 1), not from the
     whole run: upstream documents that the first time windows need many coupling
     iterations, so gating the start-up transient would be a spurious NO-GO about
     something the analysis never looks at.
  K2 the supervisor's coupled-status.json exists, and either both participants exited
     cleanly or the run stopped_by == "ceiling" with EVERY participant still running at
     SIGTERM (i.e. every recorded state is "killed"). A ceiling stop in which one
     participant had already exited is a desynchronised coupling wearing a budget
     outcome's clothes, and is refused. participant-died is a loud failure.
  K3 diagnostics, never gated: mean/max iterations per window, per-iteration residuals,
     IQN-ILS filter drops.

S - periodic steady state (the analysis window is DERIVED, never chosen)
  S1 every signal is segmented at ONE period, taken from the transverse tip displacement.
     Streamwise displacement, drag and lift are the second harmonic; segmenting them at
     their own dominant frequency makes per-cycle amplitudes alternate between
     half-strokes and spuriously fails S3.
  S2 the first 4.0 s of physical time is discarded unconditionally (the inlet ramp ends
     at t = 2 s; the published reference window begins at t = 5 s).
  S3 detect_cycle_convergence (window 3, mean-drift 1 %, amplitude-drift 2 %) reports
     converged on the transverse signal with a settled tail of at least 4 full cycles
     inside t >= 4.0 s. The analysis window IS that settled tail.
  S4 the driver checkpoints as further cycles complete, and the verdict is taken from the
     LAST checkpoint at the stopping time - never the best. Every checkpoint ships in the
     bundle.
  S5 CUMULATIVE bound: across the settled tail, the first-to-last relative change of the
     per-cycle mean and of the per-cycle amplitude must each stay within 2 %. S3 compares
     ADJACENT cycles only, so without S5 a record growing 1.2 % per cycle satisfies it
     without limit while the amplitude grows 30 % across the window - which is what a
     slowly saturating added-mass instability looks like, i.e. the realistic FSI3 failure
     mode. On the published reference the cumulative drift is 0.25 % over seven cycles,
     so the bound accepts genuine data with two orders of magnitude to spare.
     n_settled_cycles reports the cycles actually averaged into the gated statistics, not
     the detector's count, and must itself meet the S3 minimum.

D - displacement bands (the physics gate, relative to R3)
  D1 flag-tip transverse amplitude within 15 %.
  D2 flag-tip fundamental frequency within 5 %.
  D3 flag-tip streamwise amplitude within 25 %.
  D4 flag-tip streamwise mean within 25 %.
  D5 flag-tip streamwise frequency within 5 % - a structural harmonic check, declared
     CORRELATED with D2 and not independent evidence.

X - diagnostics, never gated: transverse MEAN (period-conditioned: a 1.5 % change in the
  assumed period moves it ~50 %, measured on the reference itself); drag and lift mean and
  amplitude; iterations per window; the featflow-table cross-check deltas; the I2
  comparison; and the refined-mesh campaign in its entirety.

VERDICT: GO if and only if P and C and I1 and I3 and R and K1 and K2 and S3 and D1..D5
all pass. I2 and X are reported, never gated. NO-GO means: ship the adapter, the harness
and the loud gate, and record the miss and the infrastructure gap honestly. No band is
relaxed under any circumstance.

BUDGET (pre-declared): aero-dev only, serial, no cloud spend.
  B1 pre-flight (I1-I4) ceiling 3600 s.
  B2 gated campaign: rung blockMeshDict (the ~21k-cell upstream default), max-time 8.0 s,
     ceiling 172800 s (48 h), single run, no restarts. Reaching the ceiling is a RECORDED
     OUTCOME, not a failure; the analysis then runs on whatever the S-rule yields.
  B3 non-gated diagnostic: rung blockMeshDict_refined, same max-time and ceiling, may run
     concurrently with B2. Pre-registered as non-gated from the start so it cannot become
     a second attempt at the gate.
  B4 if S3 cannot be satisfied within B2, the verdict is NO-GO on periodic-steady-state -
     not a re-run with a hand-picked window.

CONTINGENCIES - MECHANISM (allowed, declared in advance) vs GATE (forbidden):
  M1 if the coded inlet BC will not compile in the SIF, set FOAM_ALLOW_SYSTEM_OPERATIONS
     and a writable WM_PROJECT_USER_DIR; failing that, substitute the algebraically
     identical exprFixedValue form and record the substitution and a byte-diff.
  M2 a stale precice-run/ exchange directory is removed before each run; participants run
     with --no-home.
  M3 if headless gmsh fails, pre-generate the solid mesh inside the SIF at build time.
  M4 SCOPE DEGRADATION, WEAKER CLAIM: if and only if precice-fsi.sif cannot be built
     because the openfoam-adapter will not compile against OpenFOAM v2412, run
     fluid-nutils + solid-nutils instead. That verifies the harness but NOT the OpenFOAM
     participant path, so taking M4 means ADR-016 stays `proposed` and the stage verdict
     is NO-GO-with-partial-delivery.
  FORBIDDEN: changing any D band, any convergence limit, max-iterations, the S2 discard,
  the S3 tail length, the analysis window, or the reference row. Any of these requires a
  new ADR AFTER the campaign, and the original verdict stands on the record.
"""


# ---------------------------------------------------------------------------------------
# bundle helpers
# ---------------------------------------------------------------------------------------


@dataclass
class Checkpoint:
    """One analysis snapshot. The verdict is taken from the LAST one (gate S4)."""

    wall_clock_s: float
    t_end: float
    n_windows: int
    n_settled_cycles: int
    measured: dict[str, float]
    errors: dict[str, float]
    passed: dict[str, bool]

    def as_dict(self) -> dict[str, Any]:
        return {
            "wall_clock_s": self.wall_clock_s,
            "t_end": self.t_end,
            "n_windows": self.n_windows,
            "n_settled_cycles": self.n_settled_cycles,
            "measured": self.measured,
            "relative_errors": self.errors,
            "passed": self.passed,
        }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _relative(measured: float, reference: float) -> float:
    return abs(measured - reference) / abs(reference)


# ---------------------------------------------------------------------------------------
# the campaign
# ---------------------------------------------------------------------------------------


def _solverdummy_gate(
    spec: CoupledCaseSpec, args: argparse.Namespace, host_root: Path, remote_root: str
) -> dict[str, Any]:
    """Gate I1 — two dummy participants couple inside the SIF, through the real launcher.

    Seconds, not hours, and it exercises every piece of infrastructure the campaign
    depends on: apptainer exec, MPI_Init inside the unprivileged LXC, socket m2n between
    two processes, --no-home, and the supervisor script itself.

    `solverdummy.py` imports nothing from `aero`, so it is copied into the case directory
    and run directly — the SIF does not need the platform installed.
    """
    from aero.adapters.precice.solverdummy import write_solverdummy_config

    case = host_root / "solverdummy"
    case.mkdir(parents=True, exist_ok=True)
    write_solverdummy_config(case / "precice-config.xml")
    source = (
        Path(__file__).resolve().parents[1] / "aero" / "adapters" / "precice" / "solverdummy.py"
    )
    (case / "solverdummy.py").write_bytes(source.read_bytes())

    sif = f"/opt/aero/containers/{spec.container_of_record}"
    plan = CoupledLaunchPlan(
        case_root_remote=f"{remote_root}/solverdummy",
        participants=tuple(
            ParticipantSpec(
                name=name,
                workdir=".",
                command=(
                    f"python3 solverdummy.py --participant {name} --config precice-config.xml"
                ),
                sif=spec.container_of_record,
            )
            for name in ("A", "B")
        ),
        sif_paths={spec.container_of_record: sif},
        wall_clock_ceiling_s=300,
        poll_interval_s=2,
        peer_grace_s=30,
        term_grace_s=10,
    )
    executor = LocalSSHExecutor(
        host=args.host, ssh_user="root", repo_root=_REPO_ROOT, long_timeout_s=1800
    )
    outcome = launch_coupled(
        plan, executor, run_id=f"solverdummy-{datetime.now(UTC):%Y%m%d-%H%M%S}", case_root_host=case
    )
    return {
        "passed": outcome.ok,
        "stopped_by": outcome.stopped_by,
        "participants": {o.name: o.state for o in outcome.outcomes},
        "log_tails": {o.name: o.log_tail[-800:] for o in outcome.outcomes},
    }


def _preflight(spec: CoupledCaseSpec, args: argparse.Namespace) -> dict[str, Any]:
    """I-gates. Everything here must pass before a campaign solve is launched."""
    record: dict[str, Any] = {"started_at": _utc_now(), "gates": {}}

    solver = PreciceCoupledSolver(
        sif_path=f"/opt/aero/containers/{spec.container_of_record}",
        expectation=TUREK_HRON_FSI3_EXPECTATION,
        host_nfs_root=args.host_nfs_root,
        remote_nfs_root=args.remote_nfs_root,
    )
    executor = LocalSSHExecutor(
        host=args.host, ssh_user="root", repo_root=_REPO_ROOT, long_timeout_s=args.timeout
    )

    # P/C: materialize, verify every file, assert the configuration.
    case_dir = solver.prepare(spec)
    config = read_precice_config(
        case_dir.host_path / CASE_ROOT_DIRNAME / spec.case_subdir / "precice-config.xml"
    )
    record["gates"]["P1_C1_C2_C5"] = {
        "passed": True,
        "run_id": case_dir.run_id,
        "commit": spec.source.pin.commit,
        "config": list(describe(config)),
    }
    print(f"[P/C] materialized and asserted {spec.case_subdir} @ {spec.source.pin.commit[:12]}")
    for line in describe(config):
        print(f"       {line}")

    # I3: mesh, and record the cell count that identifies the rung.
    mesh = solver.mesh(case_dir, executor)
    record["gates"]["I3"] = {
        "passed": bool(mesh.ok),
        "n_cells": mesh.n_elements,
        "mesh_dict": spec.source.fluid_mesh_dict,
    }
    print(f"[I3] blockMesh ok={mesh.ok} cells={mesh.n_elements} ({spec.source.fluid_mesh_dict})")
    if not mesh.ok:
        record["verdict"] = "NO-GO (I3: blockMesh failed)"
        return record

    # I1 — infrastructure, through the real launcher.
    try:
        i1 = _solverdummy_gate(
            spec,
            args,
            host_root=case_dir.host_path,
            remote_root=str(case_dir.remote_path),
        )
    except Exception as exc:
        i1 = {"passed": False, "error": str(exc)}
    record["gates"]["I1"] = i1
    print(
        f"[I1] solverdummy coupling passed={i1['passed']} ({i1.get('stopped_by', i1.get('error'))})"
    )
    if not i1["passed"]:
        record["verdict"] = "NO-GO (I1: the infrastructure pre-flight did not couple)"
        record["finished_at"] = _utc_now()
        return record

    # I4 — calibration. Measured, so the budget decision is made from evidence.
    windows = args.calibration_windows
    calib_spec = spec.model_copy(
        update={
            "name": f"{spec.name}_calibration",
            "max_time": windows * 1e-3,
            "wall_clock_ceiling_s": min(args.timeout, 3600),
        }
    )
    calib_dir = solver.prepare(calib_spec)
    calib_mesh = solver.mesh(calib_dir, executor)
    if not calib_mesh.ok:
        record["gates"]["I4"] = {"passed": False, "reason": "blockMesh failed for the calibration"}
        record["verdict"] = "NO-GO (I4: calibration mesh failed)"
        record["finished_at"] = _utc_now()
        return record

    print(f"[I4] calibration: {windows} time windows ({calib_spec.max_time:g} s physical)")
    calib_result = solver.run(calib_dir, executor)
    calib_status = solver.coupled_status(calib_result)
    i4: dict[str, Any] = {
        "windows_requested": windows,
        "stopped_by": calib_status.stopped_by,
        "wall_clock_s": calib_status.wall_clock_s,
    }
    try:
        trace = solver.watchpoint(calib_result)
        reports = solver.coupling_report(calib_result)
        completed = trace.n_rows
        # ADR-036 I4 requires a calibration of at least the requested length. "> 0" would
        # let a run that died after three windows report a seconds-per-window figure, and
        # that figure is what the budget decision is made from.
        i4.update(
            {
                "passed": completed >= windows and calib_status.stopped_by == "all-exited",
                "windows_completed": completed,
                "seconds_per_window": (
                    calib_status.wall_clock_s / completed if completed else None
                ),
                "mean_iterations": [r.mean_iterations for r in reports],
                "max_iterations": [r.max_observed_iterations for r in reports],
                "n_nonconverged": [r.n_nonconverged for r in reports],
            }
        )
        if completed:
            per_window = calib_status.wall_clock_s / completed
            i4["projection"] = {q: per_window * q / 1e-3 / 3600.0 for q in (2.0, 6.0, 8.0, 15.0)}
            print(
                f"[I4] {completed} windows in {calib_status.wall_clock_s:.0f}s "
                f"= {per_window:.2f} s/window"
            )
            for target, hours in sorted(i4["projection"].items()):
                print(f"       projected to t = {target:g} s: {hours:.1f} h")
    except Exception as exc:
        i4.update({"passed": False, "error": str(exc)})
    record["gates"]["I4"] = i4
    if not i4.get("passed"):
        record["verdict"] = "NO-GO (I4: the calibration run produced no readable coupling)"
        record["finished_at"] = _utc_now()
        return record

    record["verdict"] = "PRE-FLIGHT COMPLETE"
    record["case_dir"] = str(case_dir.host_path)
    record["finished_at"] = _utc_now()
    return record


def _analyse(
    solver: PreciceCoupledSolver, result: Any, spec: CoupledCaseSpec, reference: dict[str, float]
) -> Checkpoint:
    """One analysis snapshot from the watch-point as it currently stands."""
    trace = solver.watchpoint(result)
    analysis = analyse_displacement_watchpoint(
        trace, discard_s=spec.analysis_discard_s, min_cycles=spec.analysis_min_cycles
    )
    uy = analysis.of(TIP_UY)
    ux = analysis.of(TIP_UX)
    measured = {
        "tip_uy_amplitude": uy.amplitude,
        "tip_uy_frequency": analysis.fundamental_frequency,
        "tip_ux_amplitude": ux.amplitude,
        "tip_ux_mean": ux.mean,
        "tip_ux_frequency": ux.frequency,
        "tip_uy_mean_DIAGNOSTIC": uy.mean,
    }
    bands = {m.name: m.tolerance for m in TurekHronFSI3().metrics()}
    errors = {k: _relative(v, reference[k]) for k, v in measured.items() if k in bands}
    return Checkpoint(
        wall_clock_s=0.0,
        t_end=analysis.t_end,
        n_windows=trace.n_rows,
        n_settled_cycles=analysis.n_settled_cycles,
        measured=measured,
        errors=errors,
        passed={k: errors[k] <= bands[k] for k in errors},
    )


def _provenance(spec: CoupledCaseSpec, *, allow_dirty: bool) -> dict[str, Any]:
    """Gate P3 — the four-fold tuple from a clean tree, computed BEFORE anything runs.

    P3 sits inside the GO conjunction, so it has to be evaluated rather than assumed
    (Stage-18 review finding 8: a bundle claimed a rule it never checked). Computing it
    first also means a dirty tree stops the campaign in seconds instead of at the end of
    a multi-day run, when the SHA no longer describes what ran.
    """
    provenance = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif=spec.container_of_record,
        resolved_config=json.loads(spec.model_dump_json()),
        allow_dirty=allow_dirty,
    )
    return json.loads(provenance.model_dump_json())


def _campaign(spec: CoupledCaseSpec, args: argparse.Namespace) -> dict[str, Any]:
    """Full campaign: prepare, mesh, coupled run, analyse, verdict."""
    case = TurekHronFSI3(spec)
    reference = case.reference(_REPO_ROOT).scalars
    bands = {m.name: m.tolerance for m in case.metrics()}

    record: dict[str, Any] = {
        "started_at": _utc_now(),
        "spec": json.loads(spec.model_dump_json()),
        "reference": reference,
        "bands": bands,
        "gated": spec.gated,
        "checkpoints": [],
    }

    try:
        record["provenance"] = _provenance(spec, allow_dirty=args.allow_dirty)
        print(f"[P3] four-fold provenance ok: git {record['provenance']['git_sha'][:12]}")
    except ProvenanceError as exc:
        record["verdict"] = f"NO-GO (P3: {exc})"
        record["finished_at"] = _utc_now()
        return record

    solver = PreciceCoupledSolver(
        sif_path=f"/opt/aero/containers/{spec.container_of_record}",
        expectation=TUREK_HRON_FSI3_EXPECTATION,
        host_nfs_root=args.host_nfs_root,
        remote_nfs_root=args.remote_nfs_root,
    )
    executor = LocalSSHExecutor(
        host=args.host, ssh_user="root", repo_root=_REPO_ROOT, long_timeout_s=args.timeout
    )

    case_dir = solver.prepare(spec)
    record["run_id"] = case_dir.run_id
    print(f"[prepare] {case_dir.run_id} -> {case_dir.host_path}")

    mesh = solver.mesh(case_dir, executor)
    record["mesh"] = {"ok": bool(mesh.ok), "n_cells": mesh.n_elements}
    if not mesh.ok:
        record["verdict"] = "NO-GO (I3: blockMesh failed)"
        record["finished_at"] = _utc_now()
        return record
    print(f"[mesh] {mesh.n_elements} cells")

    print(f"[run] launching coupled participants, ceiling {spec.wall_clock_ceiling_s}s")
    result = solver.run(case_dir, executor)
    status = solver.coupled_status(result)
    record["coupled_status"] = json.loads(status.model_dump_json())
    print(f"[run] stopped_by={status.stopped_by} after {status.wall_clock_s:.0f}s")

    # K2 — how the run ended is recorded, and a dead participant is fatal.
    if status.stopped_by == "participant-died":
        record["verdict"] = "NO-GO (K2: a participant died; the coupled solve is partial)"
        record["finished_at"] = _utc_now()
        return record

    # K1 — coupling convergence, per participant.
    try:
        reports = solver.coupling_report(result)
        for report in reports:
            assert_coupling_converged(report)
        record["coupling"] = [
            {
                "participant": r.participant,
                "n_windows": r.n_windows,
                "mean_iterations": r.mean_iterations,
                "max_iterations": r.max_observed_iterations,
                "n_nonconverged": r.n_nonconverged,
            }
            for r in reports
        ]
    except Exception as exc:
        record["verdict"] = f"NO-GO (K1: {exc})"
        record["finished_at"] = _utc_now()
        return record

    # S — the derived analysis window, then D.
    try:
        checkpoint = _analyse(solver, result, spec, reference)
    except LimitCycleError as exc:
        record["verdict"] = f"NO-GO (S3: {exc})"
        record["finished_at"] = _utc_now()
        return record
    except (WatchpointError, PreciceSolverError, CouplingConvergenceError, ValueError) as exc:
        # _analyse reaches the watch-point reader, the config, and the solver's own
        # fail-loud checks, none of which raise LimitCycleError. Letting those escape
        # would end a multi-day campaign with a traceback and no bundle — the one outcome
        # worse than a NO-GO, because nothing is recorded.
        record["verdict"] = f"NO-GO ({type(exc).__name__}: {exc})"
        record["finished_at"] = _utc_now()
        return record

    checkpoint.wall_clock_s = status.wall_clock_s
    record["checkpoints"].append(checkpoint.as_dict())

    print("[D] measured vs reference (pre-registered bands):")
    for name, tolerance in bands.items():
        measured = checkpoint.measured[name]
        print(
            f"       {name:<20} {measured:+.6e} vs {reference[name]:+.6e}  "
            f"err {checkpoint.errors[name]:+.2%}  band {tolerance:.0%}  "
            f"{'PASS' if checkpoint.passed[name] else 'FAIL'}"
        )
    print(
        f"       {'tip_uy_mean (diag)':<20} {checkpoint.measured['tip_uy_mean_DIAGNOSTIC']:+.6e}"
        "  [never gated]"
    )

    all_passed = all(checkpoint.passed.values())
    dirty = str(record.get("provenance", {}).get("git_sha", "")).endswith("-dirty")
    if spec.gated and dirty:
        record["verdict"] = (
            "NO-GO (P3: the tree was dirty, so the recorded SHA does not describe what ran)"
        )
    elif not spec.gated:
        record["verdict"] = "DIAGNOSTIC (non-gated by pre-registration; reported, bears no verdict)"
    elif all_passed:
        record["verdict"] = "GO"
    else:
        missed = [k for k, ok in checkpoint.passed.items() if not ok]
        record["verdict"] = f"NO-GO (D: outside the pre-registered band(s): {', '.join(missed)})"

    record["finished_at"] = _utc_now()
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="aero-dev")
    parser.add_argument("--timeout", type=int, default=172800, help="Wall-clock ceiling, seconds.")
    parser.add_argument("--max-time", type=float, default=8.0, help="preCICE <max-time>, seconds.")
    parser.add_argument(
        "--mesh",
        default="blockMeshDict",
        choices=("blockMeshDict", "blockMeshDict_refined", "blockMeshDict_double_refined"),
    )
    parser.add_argument("--preflight", action="store_true", help="Run the I-gates only.")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Exploration only: log a -dirty SHA. A GATED verdict requires a clean tree.",
    )
    parser.add_argument(
        "--calibration-windows",
        type=int,
        default=200,
        help="Time windows for the I4 calibration run (ADR-036 requires >= 200).",
    )
    parser.add_argument(
        "--not-gated",
        action="store_true",
        help="Mark the run a pre-registered diagnostic (ADR-036 B3); it bears no verdict.",
    )
    parser.add_argument("--host-nfs-root", dest="host_nfs_root", type=Path, default=None)
    parser.add_argument("--remote-nfs-root", dest="remote_nfs_root", type=Path, default=None)
    parser.add_argument(
        "--out", type=Path, default=None, help="Bundle path (scratchpad by default)."
    )
    args = parser.parse_args(argv)

    from aero.adapters._base import DEFAULT_HOST_NFS_ROOT, DEFAULT_REMOTE_NFS_ROOT

    args.host_nfs_root = args.host_nfs_root or DEFAULT_HOST_NFS_ROOT
    args.remote_nfs_root = args.remote_nfs_root or DEFAULT_REMOTE_NFS_ROOT

    label = "preflight" if args.preflight else ("refined" if args.not_gated else "gated")
    out = args.out or Path(f"/tmp/stage19_{label}.json")

    spec = fsi3_case_spec(
        name="turek_hron_fsi3",
        max_time=args.max_time,
        wall_clock_ceiling_s=args.timeout,
        fluid_mesh_dict=args.mesh,
    )
    if args.not_gated:
        spec = spec.model_copy(update={"gated": False})

    print(PREREGISTERED_GATE_BLOCK)
    print()

    record = _preflight(spec, args) if args.preflight else _campaign(spec, args)
    record["preregistered_gate_block"] = PREREGISTERED_GATE_BLOCK
    record["adr"] = "ADR-036"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\n[bundle] {out}")
    print(f"[verdict] {record.get('verdict', 'INCOMPLETE')}")
    return 0 if str(record.get("verdict", "")).startswith(("GO", "PRE-FLIGHT", "DIAGNOSTIC")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
