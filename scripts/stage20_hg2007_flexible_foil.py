"""Stage 20 campaign driver — Heathcote-Gursul flexible flapping foil (ADR-039).

The operational copy of the ADR-039 gate block lives here as
``PREREGISTERED_GATE_BLOCK`` and is embedded in every bundle this driver writes; a
required unit test asserts it is byte-identical to the ADR.

Unlike the Stage-19 driver, this one NEVER holds an owning ``run_long.sh wait`` across a
solve: a campaign solve is SUBMITTED detached (``--submit``, ``--probe``) and a later
invocation — possibly a later session — re-enters through ``--collect`` /
``--collect-probe``. ``AERO_RUN_LONG_REAP=1`` makes ``wait`` the owner of a job's
lifetime, which is right for CI and fatal for a 14-day wave (operator decision,
session 6).

Modes:
  --probe ARM RUNG      prepare + mesh + submit ONE I7/I4 probe, detached; writes a
                        submission JSON next to --out.
  --collect-cost I4     attribute a finished run's per-step CPU to the linear-solver
                        work that caused it (I10), from logs already on disk - no
                        cluster, no new solve.
  --collect-probe SUB   read a finished probe: coupled status, max post-ramp Courant
                        (I7), seconds/window + iterations/window + du + time-directory
                        count (I4), into a data/vv-shaped record.
  --submit ARM          prepare + mesh + submit ONE GATED arm, detached (sentinels must
                        be filled; refuses while ADR-039 B2 is pending).
  --status SUB          run_long.sh status for a submission JSON.
  --collect SUB         gate on status {done,failed}; rebuild the spec from the
                        submission JSON, assert its config digest, reattach, load,
                        read_arm, and write the arm bundle.
  --verdict FLEX RIGID  clause-by-clause verdict from two arm bundles: A-family
                        alignment, per-signal S5, D3/D4 paired increments, D5/D6/D7
                        predicates, D9 reported. Composed only by this driver — the
                        V&V dashboard structurally cannot see these clauses.

Every bundle is ``json.dumps(record, indent=2, sort_keys=True) + "\\n"`` with
``preregistered_gate_block`` and ``adr`` at top level (the ADR-036 pattern); committed
copies go under ``data/vv/`` by hand.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import numpy as np  # noqa: E402
from aero.adapters._base import CaseDir  # noqa: E402
from aero.adapters.openfoam.solver_log import (  # noqa: E402
    read_courant_history,
    read_fluid_cost_history,
)
from aero.adapters.precice.case import (  # noqa: E402
    CASE_ROOT_DIRNAME,
    assert_provenance_describes,
    spec_config_digest,
)
from aero.adapters.precice.launcher import stage_coupled  # noqa: E402
from aero.adapters.precice.solver import PreciceCoupledSolver  # noqa: E402
from aero.orchestration.local_ssh import LocalSSHExecutor  # noqa: E402
from aero.provenance.four_fold import compute_provenance  # noqa: E402
from aero.vv.alignment import align_arms  # noqa: E402
from aero.vv.fsi.cost_model import attribute_step_cost  # noqa: E402
from aero.vv.fsi.hg2007_flexible_foil import (  # noqa: E402
    ARMS,
    FREQUENCY_HZ,
    GATED_MAX_TIME_S,
    GATED_RUNG,
    GATED_TIME_WINDOW_S,
    RUNGS,
    evaluate_predicates,
    hg2007_case_spec,
    is_gated_configuration,
)
from aero.vv.fsi.hg2007_readout import ArmReadout, read_arm  # noqa: E402
from aero.vv.fsi.preflight import signal_drift_reports  # noqa: E402
from aero.vv.paired_difference import (  # noqa: E402
    paired_delta_uncertainty,
    paired_delta_uncertainty_from_samples,
)

_ADR = _REPO_ROOT / "docs/adrs/ADR-039-hg2007-flexible-foil-gate-preregistration.md"
_BEGIN = "<!-- GATE-BLOCK:BEGIN -->"
_END = "<!-- GATE-BLOCK:END -->"

#: The candidate probe dt (ADR-039 I7) — exactly representable, and the probe max-time
#: is an exact multiple so the authored-consistency validator accepts it.
PROBE_DT_S = 3.5e-4
PROBE_N_WINDOWS = 4350  # 1.5225 s: one (1-cos) ramp cycle + half a settled cycle
PROBE_CEILING_S = 43200  # ADR-039 B1: per-submission ceiling


def gate_block_from_adr(adr_path: Path = _ADR) -> str:
    """The gate block exactly as ADR-039 states it, with one trailing newline."""
    text = adr_path.read_text(encoding="utf-8")
    inner = text.split(_BEGIN, 1)[1].split(_END, 1)[0]
    fenced = inner.strip()
    if not (fenced.startswith("```text") and fenced.endswith("```")):
        raise ValueError(f"{adr_path}: the gate block is not a ```text fence")
    return fenced.removeprefix("```text").removesuffix("```").strip("\n") + "\n"


PREREGISTERED_GATE_BLOCK = """\
THE PRE-REGISTERED GATE BLOCK (ADR-039 is the source of record; the campaign driver's
PREREGISTERED_GATE_BLOCK is the operational copy, embedded in every bundle; required
unit tests assert byte-identity and ordered band parity against CLAUSE_BANDS)

P - pins and provenance (Hard Rule 8; ADR-038 replaces ADR-036's single-SIF refusal)
  P1 OpenFOAM ESI v2412 fluid participant in precice-fsi.sif; CalculiX 2.20 (verified
     live in the SIF) + calculix-adapter v2.20.1 solid participant in
     calculix-precice.sif; preCICE v3.4.1; openfoam-adapter
     2c3062ce941915616ac763371805c57e15e02466. Both SIFs are in containers/SHA256SUMS,
     signed and apptainer-verify clean.
  P2 every gated run logs the four-fold tuple from a clean tree, computed BEFORE the
     solve. A dirty tree yields a "-dirty" SHA and the gated verdict is refused even
     under --allow-dirty, because the SHA would not describe what ran.
  P3 the provenance roster names EVERY participating SIF: compute_provenance receives
     extra_container_sifs derived from the spec, and assert_provenance_describes(spec,
     provenance) runs before anything else does. ADR-036's P3 (a gated run spanning more
     than one SIF is structurally refused) is FALSE since ADR-038; the property that
     mattered - provenance describes everything that ran - is now enforced directly.
  P4 gated is DERIVED by is_gated_configuration from (rung, time-window-size, max-time),
     never passed in. While B2 below is pending its I4 record the sentinels are None and
     NO configuration can claim the gated verdict; the pre-flight-before-campaign
     ordering is structural, not a rule to remember.
  P5 the driver refuses a gated run unless git merge-base --is-ancestor proves this
     ADR's first commit precedes the I4 record commit that fills B2.

C - configuration integrity (authored case: these bytes are what the spec renders,
  every writer re-read - ADR-037 inverts ADR-036's pinned-bytes contract)
  C1 the rendered precice-config.xml re-reads to the expectation DERIVED from the spec:
     parallel-implicit; max-iterations 50; relative convergence 5e-3 on BOTH
     Displacement and Force (the calculix-adapter reads Force, not FSI3's Stress);
     IQN-ILS with QR2 filter limit 1e-2, initial-relaxation 0.5, max-used-iterations
     100, time-windows-reused 15; the RBF support-radius is SCALED to the surface
     spacing (upstream's bare 1. is one metre on a 0.09 m chord).
  C2 the CalculiX deck re-reads to its spec: C3D8I, never C3D8; NLGEOM on
     unconditionally; *DYNAMIC DIRECT with the solid dt exactly the coupling window;
     ALPHA present and 0.0; *CLOAD declared all-zero on the interface nset, dofs 1,2,3
     (the adapter overwrites it - absent, the run is silently force-free); INC computed
     >= 50 x n_windows, never copied - 50 is the coupling's own max-iterations and ccx
     counts every attempt, so a smaller margin certifies a budget the coupling may
     legally exceed; n_through_thickness even (odd has no mid-surface node and preCICE
     snaps the watch-point silently).
  C3 ONE span feeds both writers: the emitted slab z-extent equals the emitted
     blockMeshDict span exactly (upstream's 1 m default under-loads this plate 400x
     while checkMesh passes and the coupling converges).
  C4 the solid's wetted curve IS the fluid's: surface_x equals the fluid curve
     generator's output bitwise, and the two arms differ in plate half-thickness ONLY -
     asserted at construction and again as the first statement of materialization.
  C5 watch-point headers read from the run equal the headers PREDICTED from the
     configuration; watch-points are interface vertices. No positional column indexing.
  C6 every materialized file's sha256 rides in the schema-v2 aero-manifest.json, whose
     spec_sha256 is computed by CALLING config_hash - the on-disk record and the MLflow
     tag provably describe one spec.

I - infrastructure pre-flight (ALL before any campaign run; each probe records its own
  four-fold tuple into data/vv/; a probe that fails is recorded, never adjusted in-run;
  no rate is ever extrapolated from a transient)
  I1 two solverdummy participants complete a coupling across the TWO SIFs via the real
     supervisor launcher.
  I3 blockMesh succeeds on all three rungs, both arms; cell counts equal 45682 / 77240 /
     130032 (uniform 2-D refinement ratio 1.30) and the static mesh-quality metrics are
     recorded as the baseline M3 gates against.
  I4 calibrations COMPLETE at least the requested 200 windows and end all-exited, both
     arms, every rung; seconds-per-window, iterations-per-window, the NLGEOM cost
     multiplier, the time-directory count and du are recorded BEFORE any budget or rung
     decision (forces1 writes its registered fields every step and purgeWrite does not
     track them; a full NFS mid-wave is the failure mode). A run that died early yields
     NO seconds-per-window figure.
  I5 mesh quality at the motion probe's retained output instants degrades the recorded
     static baseline within M3's margin, with M1 and M2 holding at every instant.
  I6 the coded interface-power function object compiles under the participant uid and
     its force sum reproduces force.dat.
  I7 max-Courant is MEASURED, never estimated: per arm at the gated rung plus the
     flexible arm at the fine rung, at the candidate dt 3.5e-4 s, over max-time 1.5225 s
     (4350 windows, past post-ramp peak plunge velocity - the (1-cos) ramp spans one
     full cycle, so a few-step probe would measure the wrong regime). Co <= 1 or the
     probe FAILS and is recorded; the campaign dt IS a passing probe's dt verbatim.
  I8 checkpoint fidelity: 5 windows implicit vs the same 5 at max-iterations 1,
     comparing window-start field state. backward if and only if the probe proves the
     adapter checkpoints U.oldTime().oldTime() across coupling iterations; otherwise
     Euler, declared first-order, temporal error common-mode across rungs (fixed dt).
  I9 the ccx print convention is measured before D10 is read: an uncoupled deck with a
     known applied load records whether *NODE PRINT's RF at a prescribed dof includes
     the applied *CLOAD, and the *AMPLITUDE row bound is re-measured at the campaign
     row count (70005 rows are measured fine; the campaign needs more only if a smaller
     fallback dt is forced).

R - reference integrity
  R1 the reference is identified by content digest and per-page raster digests - no raw
     PDF digest is reproducible, Bath's Pure repository re-wraps every download;
     digitization.csv carries 208 markers, three independent binarizations each, and
     hg2007_recomputed.csv carries its sha256 sidecar.
  R2 recomputed anchors agree with the text-sourced values within 15 percent: the pitch
     amplitudes (17 and 6 degrees), the Re 18000 and 27000 crossovers, both increments
     positive. PASSED 2026-07-31. The one documented disagreement - the Re 9000
     crossover misses the thesis's blanket prose by +12.6 percent while its
     condition-specific prose reproduces to 0.1 percent - is carried as a measured row,
     not smoothed over.
  R3 the reference OF RECORD is hg2007_recomputed.csv, produced by the platform's own
     estimators; the tabulated and text-sourced values are reported beside every gated
     number. A gate compared against a reference we do not understand is worse than no
     gate.

K - coupling convergence (fail-loud, enforced inside load())
  K1 ZERO time windows in the analysis window may hit max-iterations = 50, and every
     window must report convergence. The window range is DERIVED from the S-rule's
     analysis window (window-scoped, ADR-037 - the start-up transient legitimately
     iterates more and the analysis never looks at it). One non-converged window makes
     the run non-reportable - investigate, never relax.
  K2 the supervisor's coupled-status.json exists, and either both participants exited
     cleanly or the run stopped at the ceiling with EVERY participant still running at
     SIGTERM. A ceiling stop with one participant already exited is a desynchronised
     coupling wearing a budget outcome's clothes, and is refused. participant-died is a
     loud failure.
  K3 diagnostics, never gated: mean/max iterations per window, per-iteration residuals,
     IQN-ILS filter drops, and the repeat-cadence classification (every repeated time in
     force.dat and the ccx .dat is accounted for by the iterations log, or the readout
     RAISES - an unexplained repeat is silent data loss).

S - periodic steady state (the analysis window is DERIVED, never chosen)
  S1 every signal is segmented at the PRESCRIBED period T = 1.0145 s, bit-identical
     across arms; never an FFT-detected period.
  S2 the first 3/f seconds of physical time are discarded unconditionally: the (1-cos)
     ramp spans one cycle, plus two further cycles.
  S3 detect_cycle_convergence (window 3, mean-drift 1 percent, amplitude-drift 2
     percent) reports converged on the FUNDAMENTAL - the D0 pitch trace, segmented at
     the prescribed plunge period; thrust is the second harmonic and segmenting on it
     alternates half-strokes - with a settled tail of at least 20 full cycles on the
     paired rung and at least 10 on the GCI rungs. The analysis window IS that settled
     tail; n_settled_cycles reports the cycles actually averaged into the gated
     statistics and must itself meet the minimum.
  S4 the driver checkpoints as further cycles complete, and the verdict is taken from
     the LAST checkpoint at the stopping time - never the best. Every checkpoint ships
     in the bundle.
  S5 CUMULATIVE bound, PER GATED SIGNAL: across the settled tail, the first-to-last
     relative change of the per-cycle mean and of the per-cycle amplitude each stay
     inside 2 percent for the pitch trace AND for the thrust and interface-power
     series. S3 compares adjacent cycles only, and it certifies the fundamental alone -
     a thrust series still drifting under a settled pitch trace would otherwise ride
     into D1 unexamined (session-7 review, candidate 14). The driver evaluates the
     non-fundamental signals from their per-cycle series over the same tail.

A - paired-arm alignment (the increment is real only if the arms are comparable;
  enforced by align_arms, which raises rather than degrades)
  A1 both arms segment on the prescribed period, bit-identical, period_source
     "prescribed" on both.
  A2 the raw force-sample time bases are compared BITWISE across arms, both arrays
     supplied; an AlignedPair with time_base_checked False is refused for the gated
     verdict - honest absence is not evidence.
  A3 the segmentation anchors recover the same post-discard origin to 1e-9 of a period;
     equal discard does NOT imply equal origins (one dropped row moves the origin a full
     time step and every index-k pair then compares different physical intervals).
  A4 matched numerics by construction: both arms share the rung, the time-window-size,
     the max-time, the ddt scheme and the wall spacing; both are gated by the same
     derived predicate; plate half-thickness is the ONLY difference (C4).
  A5 D3 and D4 are evaluated on the SAME AlignedPair window (shared pair_start and
     n_pairs); the efficiency series is sliced to that window explicitly, because the
     two estimators would otherwise window independently and silently pair different
     physical cycles.

D - fidelity bands (the physics gate, relative to R3; sized by the pre-registered rule
  4 x u95_ref/|value|, floored 0.25, capped 0.50 - the cap never binds, the floor binds
  four of five, so where the floor binds the band is a POLICY number, stated as such;
  every reference value is a row of hg2007_recomputed.csv)
  D0 flexible-arm pitch amplitude, reference 5.34637 degrees (Fig 5.13a), within 25 %
     (raw rule 6.5 percent; the floor binds).
  D1 flexible-arm thrust coefficient, reference 1.00772, within 25 % (raw rule 20.6
     percent; the floor binds).
  D2 flexible-arm efficiency, reference 0.175279, within 40 % (raw rule 40.1 percent -
     the one band the rule actually set).
  D3 the thrust increment dC_T, flexible minus rigid, reference 0.609257, within 25 %
     (raw rule 2.1 percent; the floor binds and 0.25 is policy. ADR-022 measured the
     platform's 2-D solve missing HG's absolute rigid thrust by -28/+58 percent; if
     that error is multiplicative and common-mode the increment inherits it, so a D3
     NO-GO is at least as likely as a D1 NO-GO).
  D4 the efficiency increment d_eta, reference 0.0865273, within 25 % (raw rule 0.0 -
     the increment's axis and gauge terms cancel by construction; the floor binds and
     0.25 is policy).
  D5 the SIGN of the thrust increment: dC_T positive (no band). HG's headline claim; a
     negative increment is a real physical NO-GO, resolved clause by clause, never an
     exception.
  D6 the SIGN of the efficiency increment: d_eta positive (no band). Same standing as
     D5, from Fig 5.9a.
  D7 admissibility (no band): both arms report positive thrust and efficiency strictly
     between 0 and 1. An inadmissible arm RAISES - a broken record, not a NO-GO.
  D8 rigid-arm pitch amplitude within 2 deg absolute (text-sourced: the 4.23e-3 plate
     measured below two degrees at the rig's highest frequency; at the gated point the
     thesis reports below one degree).
  D9 the naive-power bias (P1-P2)/P2 on BOTH arms (no band), REPORTED-ONLY: D8 admits
     enough rigid-arm pitch to move the trailing edge 12 percent of the plunge velocity
     amplitude, and P1 assumes a single rigid-body velocity, so D8 and a gated D9 could
     not both be satisfiable in the worst admissible case (session-4 operator decision).
  D10 the interface-power closure |P3-P2|/P2 within 2 % - a genuine identity: with
     ALPHA 0 and no damping the cycle-mean reaction power over the prescribed region
     equals the interface power exactly, and holding also proves ALPHA=0 held. The I9
     record states whether the printed RF includes the applied *CLOAD, i.e. whether the
     identity closes exactly or with a nose-cap-sized residual.

M - mesh integrity (absolute gates chosen from measured failure modes; the platform's
  own checkMesh verdicts are unusable as absolutes - they fail the stock NACA 0012)
  M1 zero negative volumes, at rest and at every retained motion instant.
  M2 max skewness at most 4, at rest and at every retained motion instant (ADR-024's
     real failure was skewness 5503 with 18145 inverted cells - catastrophic, not
     marginal).
  M3 motion degradation: max non-orthogonality at the motion probe's retained instants
     exceeds the recorded static baseline by at most 2.0 degrees (the whole rung
     family's static spread is about 1.1 degrees; twice that is the margin), and stays
     below 89 degrees outright.
  M4 the cell count equals the pre-registered rung count exactly - the count is what
     identifies the rung, and the solver refuses a count it cannot parse.
  checkMesh's "Mesh OK" and the non-ortho-65 gate are REPORTED, never gated: both fail
  the platform's own production airfoil mesh at the pre-registered spacing (aspect
  ratio 1884.4471, byte-identical between the HG section and the stock NACA 0012).

X - diagnostics, never gated: D9's naive-power bias on both arms; iterations per
  window; the checkMesh report; the Re 9000 crossover disagreement (carried as
  measured); C_P as C_T/eta (derived, not an independent check of the efficiency
  definition); the time-directory footprint against the I4 projection.

VERDICT: resolved CLAUSE BY CLAUSE in the bundle, so that "NO-GO on absolute fidelity,
GO on the flexibility increment" is expressible - each clause carries its own pass. GO
if and only if P and C and I1 and I3 and I4 and I5 and I6 and I7 and I8 and I9 and R
and K1 and K2 and S1 and S2 and S3 and S4 and S5 and A1 and A2 and A3 and A4 and A5 and
M1 and M2 and M3 and M4 and D0 and D1 and D2 and D3 and D4 and D5 and D6 and D7 and D8
and D10 all pass. D9 and X are reported, never gated. The increment clauses D3 D4 D5 D6
and the predicate D7 have NO V&V dashboard row - they need both arms, the registry
report folds over one arm's metrics() alone, and only the campaign driver's bundle
carries them; a green dashboard is NOT a verdict. NO-GO means: ship the harness, the
driver and the loud gates, and record the miss and the model-form gap honestly. No band
is relaxed under any circumstance.

BUDGET (pre-declared): aero-dev only, serial per participant, no cloud spend, two waves.
  B1 pre-flight ceiling 172800 s total, 43200 s per submission (ADR-036's 3600 s floor
     is far too small here: the I7 probes are cycle-scale by design and six I4
     calibrations of at least 200 windows ride with them).
  B2 gated campaign: <<B2-PENDING-I4>>
     The sizing RULE is pre-registered now; the numbers are an OUTPUT of the I4/I7
     record via aero/vv/fsi/hg2007_sizing.py:size_gated_campaign, re-derived by a
     required test. The gated rung is mid, both arms; the time-window-size is the
     Co-passing probe's dt verbatim (never scaled from a measurement at another dt);
     max-time is the smallest exact multiple of dt covering the S2 discard plus 20
     settled cycles; the wall-clock projection uses the CONTENTION-MEASURED
     seconds-per-window (the mid-rung probes run both arms concurrently - the wave-1
     shape); dt is FIXED across all three rungs so temporal error is common-mode (I8),
     which is why I7 must also pass on the fine rung.
  B3 wave 1 is the mid rung, both arms concurrently - the paired increment, the
     headline. Wave 2 is the coarse and fine rungs - the GCI term feeding
     u95_delta_numerical. Per-wave ceiling 1209600 s (14 days). An overrun costs the
     GCI term, never the headline increment.
  B4 reaching a ceiling is a RECORDED OUTCOME, not a failure; the analysis runs on
     whatever the S-rule yields. The declared last resorts, in order: cut settled
     cycles (never below 10), then a budget NO-GO. If S3 cannot be satisfied within the
     ceiling the verdict is NO-GO on periodic steady state - not a re-run with a
     hand-picked window.

CONTINGENCIES - MECHANISM (allowed, declared in advance) vs GATE (forbidden); items are
  N-prefixed because M is a gate family here, unlike ADR-036:
  N1 a stale precice-run/ exchange directory is removed before each run; participants
     run with --no-home and a writable tmpfs; every participant runs as the case uid.
  N2 if the coded interface-power FO will not compile in the SIF at campaign scale, set
     FOAM_ALLOW_SYSTEM_OPERATIONS and a writable WM_PROJECT_USER_DIR; failing that the
     run STOPS - P2 has no fallback formula, because D9 exists precisely to show the
     naive one is biased.
  N3 if a wave-1 solve ends participant-died (an infrastructure death, which K2 already
     refuses as evidence), the wave may be resubmitted ONCE, both arms together under
     new run ids, and BOTH bundles ship. A second death is a NO-GO on infrastructure.
     This is a declared deviation from ADR-036's no-restart rule: a 14-day exposure is
     not a 48-hour one, and a died run carries no gated numbers to retry.
  N4 SCOPE DEGRADATION, WEAKER CLAIM: there is no single-container fallback for this
     claim - the CalculiX solid is the point (ADR-016). If the two-container coupling
     cannot be launched at campaign scale, the stage verdict is
     NO-GO-with-partial-delivery.
  FORBIDDEN: changing any D band, any convergence limit, max-iterations, the S2
  discard, the settled-cycle minima, the analysis window, the reference row, the motion
  margin of M3, or the sizing rule after the I4 record. Any of these requires a new ADR
  AFTER the campaign, and the original verdict stands on the record.
"""


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _write_bundle(record: dict[str, Any], out: Path) -> None:
    record.setdefault("preregistered_gate_block", PREREGISTERED_GATE_BLOCK)
    record.setdefault("adr", "ADR-039")
    record.setdefault("finished_at", _utc_now())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"bundle written: {out}")


def _provenance(spec: Any, *, allow_dirty: bool) -> dict[str, Any]:
    """P2/P3: the four-fold tuple with the full roster, BEFORE anything runs."""
    provenance = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif=spec.container_of_record,
        resolved_config=json.loads(spec.model_dump_json()),
        allow_dirty=allow_dirty,
        extra_container_sifs=spec.extra_container_sifs,
    )
    assert_provenance_describes(spec, provenance)
    dumped: dict[str, Any] = json.loads(provenance.model_dump_json())
    return dumped


def _solver(args: argparse.Namespace) -> PreciceCoupledSolver:
    kwargs: dict[str, Any] = {}
    if args.host_nfs_root:
        kwargs["host_nfs_root"] = Path(args.host_nfs_root)
    if args.remote_nfs_root:
        kwargs["remote_nfs_root"] = Path(args.remote_nfs_root)
    return PreciceCoupledSolver(**kwargs)


def _executor(args: argparse.Namespace, *, timeout_s: int) -> LocalSSHExecutor:
    return LocalSSHExecutor(
        host=args.host, ssh_user="root", repo_root=_REPO_ROOT, long_timeout_s=timeout_s
    )


def _run_long(*run_long_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_REPO_ROOT / "scripts/run_long.sh"), *run_long_args],
        capture_output=True,
        text=True,
        check=False,
    )


def _submission(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "stage20-submission-v1":
        raise SystemExit(f"{path} is not a stage20-submission-v1 file")
    return dict(data)


def _prepare_and_submit(
    args: argparse.Namespace,
    *,
    arm: str,
    rung: str,
    time_window_size: float,
    max_time: float,
    gated_intent: bool,
    label: str,
) -> Path:
    """prepare -> mesh (sync) -> stage -> submit detached -> persist the submission."""
    spec = hg2007_case_spec(
        arm=arm,  # type: ignore[arg-type]
        rung=rung,
        time_window_size=time_window_size,
        max_time=max_time,
        wall_clock_ceiling_s=args.timeout,
    )
    if gated_intent and not spec.gated:
        raise SystemExit(
            "refusing a gated submit: is_gated_configuration returned False — either the "
            "sentinels are unfilled (ADR-039 B2 pending) or this is not the gated "
            "configuration"
        )
    provenance = _provenance(spec, allow_dirty=args.allow_dirty)

    solver = _solver(args)
    executor = _executor(args, timeout_s=args.timeout)
    print(f"prepare: materializing the authored case ({arm}, rung {rung})")
    case_dir = solver.prepare(spec)
    print("mesh: blockMesh for the fluid participant (sync)")
    mesh = solver.mesh(case_dir, executor)
    if not mesh.ok:
        raise SystemExit(f"NO-GO (I3: blockMesh failed): {mesh.failure}")

    plan = solver.launch_plan(case_dir)
    staged = stage_coupled(
        plan,
        run_id=case_dir.run_id,
        case_root_host=Path(case_dir.host_path) / CASE_ROOT_DIRNAME,
    )
    submit = executor.submit_detached(staged.command, session=staged.session)
    if submit.transport_failed or submit.returncode != 0:
        raise SystemExit(f"submit failed: {submit.stderr}")

    submission = {
        "schema": "stage20-submission-v1",
        "adr": "ADR-039",
        "label": label,
        "arm": arm,
        "rung": rung,
        "run_id": case_dir.run_id,
        "session": staged.session,
        "host": args.host,
        "ssh_user": "root",
        "spec_knobs": {
            "arm": arm,
            "rung": rung,
            "time_window_size": time_window_size,
            "max_time": max_time,
            "wall_clock_ceiling_s": args.timeout,
        },
        "spec_sha256": spec_config_digest(spec),
        "gated": spec.gated,
        "case_host_path": str(case_dir.host_path),
        "case_remote_path": str(case_dir.remote_path),
        "mesh": {"ok": mesh.ok, "n_elements": mesh.n_elements},
        "provenance": provenance,
        "submitted_at": _utc_now(),
        "poll": {
            "status": f"scripts/run_long.sh status root@{args.host} {staged.session}",
            "logs": f"scripts/run_long.sh logs root@{args.host} {staged.session}",
        },
    }
    out = Path(args.out or f"/tmp/stage20_submission_{label}_{arm}_{rung}.json")
    out.write_text(json.dumps(submission, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"submitted DETACHED as {staged.session}; submission JSON: {out}")
    print(f"  poll: {submission['poll']['status']}")
    return out


def _reattach(args: argparse.Namespace, submission: dict[str, Any]) -> tuple[Any, Any, Any]:
    """Gate on {done, failed}, recover rc, rebuild the spec, and reattach."""
    session = submission["session"]
    target = f"root@{submission['host']}"
    status = _run_long("status", target, session)
    state = status.stdout.strip() or status.stderr.strip()
    if status.returncode == 2:
        raise SystemExit(f"{session} is still RUNNING — poll, do not collect. ({state})")
    if status.returncode not in (0, 1):
        raise SystemExit(
            f"{session} is in state {status.returncode} ({state}) — a vanished job has no "
            "rc file and no honest numbers; investigate before collecting"
        )
    executor = _executor(args, timeout_s=600)
    rc_result = executor.run(f"cat ~/.aero-jobs/{session}/rc")
    if rc_result.returncode != 0:
        raise SystemExit(f"cannot read {session}'s rc file: {rc_result.stderr}")
    executor_returncode = int(rc_result.stdout.strip())

    spec = hg2007_case_spec(
        arm=submission["spec_knobs"]["arm"],
        rung=submission["spec_knobs"]["rung"],
        time_window_size=submission["spec_knobs"]["time_window_size"],
        max_time=submission["spec_knobs"]["max_time"],
        wall_clock_ceiling_s=submission["spec_knobs"]["wall_clock_ceiling_s"],
    )
    digest = spec_config_digest(spec)
    if digest != submission["spec_sha256"]:
        raise SystemExit(
            "the rebuilt spec's config digest does not match the submission's "
            f"({digest} != {submission['spec_sha256']}) — the code moved under a live "
            "campaign (sentinel fill, rung edit, or default drift); the record no longer "
            "describes the run and collecting would silently mix configurations"
        )
    solver = _solver(args)
    case_dir = CaseDir(
        run_id=submission["run_id"],
        spec=spec,
        host_path=Path(submission["case_host_path"]),
        remote_path=Path(submission["case_remote_path"]),
    )
    result = solver.reattach(case_dir, executor_returncode=executor_returncode)
    return solver, case_dir, result


def _collect_probe(args: argparse.Namespace) -> int:
    """I7 + I4 from one finished probe run."""
    submission = _submission(Path(args.collect_probe))
    record: dict[str, Any] = {
        "started_at": _utc_now(),
        "submission": submission,
        "gated": False,
        "kind": "preflight-probe",
    }
    solver, case_dir, result = _reattach(args, submission)
    status = solver.coupled_status(result)
    record["coupled_status"] = json.loads(status.model_dump_json())

    case_root = Path(case_dir.host_path) / CASE_ROOT_DIRNAME
    fluid_log = case_root / "Fluid.log"
    period = 1.0 / FREQUENCY_HZ
    history = read_courant_history(fluid_log)
    # A run shorter than the post-ramp window is a CALIBRATION record (I4), not an I7
    # pass: max Co over its own span is reported, and `passed` stays None so nothing
    # downstream can mistake a short record for a post-ramp Courant measurement.
    covers_post_ramp = max(history.t) >= period
    record["i7"] = {
        "dt": submission["spec_knobs"]["time_window_size"],
        "arm": submission["arm"],
        "rung": submission["rung"],
        "courant_lines": history.n_lines,
        "max_courant_post_ramp": history.max_over(t_start=period) if covers_post_ramp else None,
        "max_courant_anywhere": max(history.max),
        "post_ramp_window_starts_at": period,
        "covers_post_ramp_window": covers_post_ramp,
        "passed": (history.max_over(t_start=period) <= 1.0) if covers_post_ramp else None,
    }

    reports = solver.coupling_report(result)
    per_participant = {
        r.participant: {
            "n_windows": r.n_windows,
            "mean_iterations": r.mean_iterations,
            "n_nonconverged": r.n_nonconverged,
        }
        for r in reports
    }
    executor = _executor(args, timeout_s=600)
    case_subdir = submission["run_id"]
    remote_case_root = f"{submission['case_remote_path']}/{CASE_ROOT_DIRNAME}"
    du = executor.run(f"du -sb {remote_case_root}")
    time_dirs = executor.run(
        f"find {remote_case_root} -maxdepth 3 -type d -regex '.*/[0-9.]+' | wc -l"
    )
    windows_requested = round(
        submission["spec_knobs"]["max_time"] / submission["spec_knobs"]["time_window_size"]
    )
    fluid = per_participant.get("Fluid", {})
    record["i4"] = {
        "arm": submission["arm"],
        "rung": submission["rung"],
        "dt": submission["spec_knobs"]["time_window_size"],
        "windows_requested": windows_requested,
        "windows_completed": int(fluid.get("n_windows", 0)),
        "stopped_by": status.stopped_by,
        "wall_clock_s": status.wall_clock_s,
        "iterations_per_window_mean": float(fluid.get("mean_iterations", 0.0)),
        "du_bytes": int(du.stdout.split()[0]) if du.returncode == 0 and du.stdout else -1,
        "time_dir_count": int(time_dirs.stdout.strip()) if time_dirs.returncode == 0 else -1,
        "concurrent_with": list(args.concurrent_with or ()),
        "coupling": per_participant,
        "case_subdir": case_subdir,
    }
    _write_bundle(record, Path(args.out or "/tmp/stage20_probe_collected.json"))
    ok = record["i7"]["passed"] and status.stopped_by == "all-exited"
    print(
        f"I7 max post-ramp Courant: {record['i7']['max_courant_post_ramp']:.4f} "
        f"(passed={record['i7']['passed']}); stopped_by={status.stopped_by}"
    )
    return 0 if ok else 1


#: The regressor grouping the cost split uses. `p` and `pcorr` are ONE pressure-solve
#: regressor: they are the same GAMG on the same matrix structure, they move together
#: across the record, and asking for their separate coefficients is exactly the
#: rank-deficient question `attribute_step_cost` refuses.
_COST_GROUPS = {"gamg_pressure": ("p", "pcorr"), "momentum": ("Ux", "Uy")}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_bytes(root: Path) -> int:
    """Apparent size of a subtree, matching ``du -sb`` (which counts ``st_size``)."""
    if root.is_file():
        return root.stat().st_size
    total = 0
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            total += path.stat().st_size
    return total


def _disk_decomposition(case_root: Path) -> dict[str, Any]:
    """Split a finished case's footprint into terms that GROW and terms that do not.

    I4 recorded one number (343 MB per 500 windows) and the handoff attributed it to
    ``forces1``'s untracked field writes. That attribution decides which lever is worth
    building, so it is split here rather than assumed.
    """
    participants = [
        d for d in case_root.iterdir() if d.is_dir() and not d.name.startswith("precice-")
    ]
    if len(participants) != 1:
        raise SystemExit(
            f"{case_root}: expected exactly one case subdirectory, found "
            f"{[d.name for d in participants]}"
        )
    case = participants[0]
    fluid = case / "fluid-openfoam"
    solid = case / "solid-calculix"
    time_dirs = [d for d in fluid.iterdir() if d.is_dir() and d.name.replace(".", "", 1).isdigit()]
    frd = list(solid.glob("*.frd"))
    terms = {
        "solid_results_frd": sum(_tree_bytes(f) for f in frd),
        "solid_other": _tree_bytes(solid) - sum(_tree_bytes(f) for f in frd),
        "fluid_time_directories": sum(_tree_bytes(d) for d in time_dirs),
        "fluid_post_processing": _tree_bytes(fluid / "postProcessing"),
        "fluid_mesh_static": _tree_bytes(fluid / "constant") + _tree_bytes(fluid / "system"),
        "participant_logs": sum(_tree_bytes(f) for f in case_root.glob("*.log")),
    }
    total = _tree_bytes(case_root)
    return {
        "total_bytes": total,
        "bytes_by_term": terms,
        "n_fluid_time_directories": len(time_dirs),
        "share_by_term": {name: value / total for name, value in terms.items()},
        # Everything except the static mesh grows with window count; the mesh does not.
        "growing_bytes": total - terms["fluid_mesh_static"],
    }


def _collect_cost(args: argparse.Namespace) -> int:
    """I10: where the measured seconds-per-window actually went, from logs already written.

    Reads the committed I4 record, finds the runs it describes, and attributes each arm's
    per-step CPU. No cluster, no new solve: the evidence was written by a run that has
    already happened, which is the only reason a cost split is affordable at all.
    """
    record_path = Path(args.collect_cost).resolve()
    i4 = json.loads(record_path.read_text(encoding="utf-8"))
    arms: dict[str, Any] = {}
    logs: dict[str, Any] = {}

    for arm, bundle in sorted(i4["collection_bundles"].items()):
        submission = bundle["submission"]
        case_root = Path(submission["case_host_path"]) / CASE_ROOT_DIRNAME
        fluid_log = case_root / "Fluid.log"
        if not fluid_log.exists():
            raise SystemExit(
                f"{fluid_log} is gone — the cost split reads the run's own bytes, and a "
                "record derived from a log that no longer exists cannot be re-checked"
            )
        history = read_fluid_cost_history(fluid_log)
        attribution = attribute_step_cost(history, groups=_COST_GROUPS)
        calibration = bundle["i4"]
        windows = int(calibration["windows_completed"])
        logs[arm] = {
            "path": str(fluid_log),
            "sha256": _sha256(fluid_log),
            "bytes": fluid_log.stat().st_size,
        }
        arms[arm] = {
            "run_id": submission["run_id"],
            # Copied VERBATIM from the run that produced these bytes. Recomputing the
            # four-tuple here would staple today's git SHA to a run from 2026-08-10.
            "provenance": submission["provenance"],
            "windows_completed": windows,
            "wall_clock_s": calibration["wall_clock_s"],
            "seconds_per_window": calibration["wall_clock_s"] / windows,
            "iterations_per_window_mean": calibration["iterations_per_window_mean"],
            "cost": {
                "n_fluid_step_solves": history.n_steps,
                "total_execution_s": history.total_execution_s,
                "total_clock_s": history.total_clock_s,
                "cpu_fraction_of_wall": history.cpu_fraction_of_wall,
                "mean_seconds_per_step": history.mean_seconds_per_step,
                "fields_solved": list(history.fields()),
                "pressure_solves_per_step": sorted(
                    {s.solves_by_field.get("p", 0) for s in history.steps}
                ),
                "solver_by_field": history.steps[-1].solver_by_field,
            },
            "attribution": json.loads(attribution.model_dump_json()),
            "disk": _disk_decomposition(case_root),
        }

    flexible = arms["flexible"]
    non_compute = {arm: 1.0 - a["cost"]["cpu_fraction_of_wall"] for arm, a in sorted(arms.items())}
    record = {
        "kind": "cost-split",
        "clause": "I10",
        "gated": False,
        "derived_from": {
            "record": {
                "path": str(record_path.relative_to(_REPO_ROOT)),
                "sha256": _sha256(record_path),
            },
            "logs": logs,
        },
        "cost_groups": {k: list(v) for k, v in _COST_GROUPS.items()},
        "arms": arms,
        "bounds": {
            "non_compute_wall_fraction": non_compute,
            "per_step_overhead_share": {
                arm: a["attribution"]["intercept_share"] for arm, a in sorted(arms.items())
            },
            "note": (
                "Both are bounds AT THE MEASURED RATE. Halving the compute leaves the same "
                "absolute overhead seconds against half the wall, so every share here must "
                "be re-read at each rung of a speed-up ladder rather than carried forward."
            ),
        },
        "verdict": (
            "MEASURED. The fluid participant's own CPU is "
            f"{flexible['cost']['cpu_fraction_of_wall'] * 100:.2f} percent of the flexible "
            "arm's wall clock, so EVERY lever that attacks I/O, preCICE exchange or waiting "
            f"on the solid is bounded by {non_compute['flexible'] * 100:.2f} percent - "
            "forces1 write scheduling is refuted as a cost lever by that bound. Fluid "
            "subcycling is bounded by the same figure plus the per-step overhead share "
            f"({flexible['attribution']['intercept_share'] * 100:.1f} percent, of which only "
            "1 in K recurs), because the total fluid step-solve count is invariant in the "
            "subcycling factor. What remains is the pressure solve: "
            f"{flexible['attribution']['share_by_group']['gamg_pressure'] * 100:.1f} percent "
            f"of fluid CPU at "
            f"{flexible['attribution']['seconds_per_iteration_by_group']['gamg_pressure'] * 1e3:.2f}"
            " ms per GAMG iteration and "
            f"{flexible['attribution']['mean_iterations_by_group']['gamg_pressure']:.0f} "
            "iterations per fluid step. Disk growth is dominated by the CalculiX .frd "
            f"({flexible['disk']['share_by_term']['solid_results_frd'] * 100:.0f} percent), "
            "which nothing in this repo reads, not by the fluid field writes "
            f"({flexible['disk']['share_by_term']['fluid_time_directories'] * 100:.0f} percent)."
        ),
    }
    _write_bundle(record, Path(args.out or "/tmp/stage20_cost_split.json"))
    for arm, entry in sorted(arms.items()):
        print(
            f"{arm}: {entry['cost']['mean_seconds_per_step']:.3f} s/step over "
            f"{entry['cost']['n_fluid_step_solves']} solves; CPU "
            f"{entry['cost']['cpu_fraction_of_wall'] * 100:.2f}% of wall; "
            f"pressure share {entry['attribution']['share_by_group']['gamg_pressure'] * 100:.1f}%"
        )
    return 0


def _collect_arm(args: argparse.Namespace) -> int:
    """One gated arm: reattach, load (K/C/S gates), read_arm, bundle."""
    submission = _submission(Path(args.collect))
    record: dict[str, Any] = {
        "started_at": _utc_now(),
        "submission": submission,
        "gated": submission["gated"],
        "kind": "arm",
    }
    solver, _case_dir, result = _reattach(args, submission)
    try:
        readout = read_arm(solver, result, arm=submission["arm"])
    except Exception as exc:
        record["verdict"] = f"NO-GO ({type(exc).__name__}: {exc})"
        _write_bundle(record, Path(args.out or f"/tmp/stage20_arm_{submission['arm']}.json"))
        return 1
    record["arm_readout"] = json.loads(readout.model_dump_json())
    drift = signal_drift_reports(readout.analysis, signals=("c_t", "c_p"))
    record["s5_per_signal"] = [json.loads(r.model_dump_json()) for r in drift]
    record["s5_all_passed"] = all(r.passed for r in drift)
    _write_bundle(record, Path(args.out or f"/tmp/stage20_arm_{submission['arm']}.json"))
    return 0


def _verdict(args: argparse.Namespace) -> int:
    """Clause-by-clause: the increment lives ONLY here (no dashboard row — ADR-039)."""
    flexible_bundle = json.loads(Path(args.verdict[0]).read_text(encoding="utf-8"))
    rigid_bundle = json.loads(Path(args.verdict[1]).read_text(encoding="utf-8"))
    flexible = ArmReadout.model_validate(flexible_bundle["arm_readout"])
    rigid = ArmReadout.model_validate(rigid_bundle["arm_readout"])

    clauses: dict[str, bool] = {}
    record: dict[str, Any] = {
        "started_at": _utc_now(),
        "kind": "verdict",
        "arms": {"flexible": flexible_bundle["submission"], "rigid": rigid_bundle["submission"]},
    }

    # A-family: refusal is the mechanism; a raise here IS the NO-GO evidence.
    aligned = align_arms(
        flexible.analysis,
        rigid.analysis,
        baseline_t=np.asarray(flexible.force_t, dtype=np.float64),
        candidate_t=np.asarray(rigid.force_t, dtype=np.float64),
    )
    if not aligned.time_base_checked:
        raise SystemExit("A2: the pair's time base was not checked — refused for a verdict")
    record["aligned_pair"] = json.loads(aligned.model_dump_json())
    clauses["A"] = True

    # S5 per gated signal, both arms (ADR-039; review candidate 14).
    s5 = {
        "flexible": [
            json.loads(r.model_dump_json())
            for r in signal_drift_reports(flexible.analysis, signals=("c_t", "c_p"))
        ],
        "rigid": [
            json.loads(r.model_dump_json())
            for r in signal_drift_reports(rigid.analysis, signals=("c_t", "c_p"))
        ],
    }
    record["s5_per_signal"] = s5
    clauses["S5"] = all(r["passed"] for arm in s5.values() for r in arm)

    # D7 first — it raises on an inadmissible arm; D5/D6 report.
    predicates = evaluate_predicates(flexible, rigid)
    for predicate in predicates:
        record.setdefault("predicates", []).append(json.loads(predicate.model_dump_json()))
        clauses[predicate.clause] = predicate.passed

    # D3/D4: the paired increments, on the SAME AlignedPair window (A5).
    d3 = paired_delta_uncertainty(
        rigid.analysis.cycles["c_t"],
        rigid.analysis.convergence,
        flexible.analysis.cycles["c_t"],
        flexible.analysis.convergence,
    )
    record["d3_paired"] = json.loads(d3.model_dump_json())
    start, count = aligned.pair_start, aligned.n_pairs
    d4 = paired_delta_uncertainty_from_samples(
        tuple(rigid.eta_per_cycle[start : start + count]),
        tuple(flexible.eta_per_cycle[start : start + count]),
        period=aligned.period,
        pair_start=start,
    )
    record["d4_paired"] = json.loads(d4.model_dump_json())
    reference = {"d_c_t": 0.609257, "d_eta": 0.0865273}
    clauses["D3"] = abs(d3.mean_delta - reference["d_c_t"]) <= 0.25 * abs(reference["d_c_t"])
    clauses["D4"] = abs(d4.mean_delta - reference["d_eta"]) <= 0.25 * abs(reference["d_eta"])
    record["reference"] = reference
    record["d9_reported"] = {
        "flexible_p1_p2_bias": flexible.p1_p2_bias,
        "rigid_p1_p2_bias": rigid.p1_p2_bias,
    }

    go = all(clauses.values())
    record["verdict"] = {
        "go": go,
        "rule": "GO <=> every ADR-039 clause; this bundle carries the driver-only "
        "clauses (A, S5 per signal, D3-D7, D9 reported) — the dashboard cannot",
        "clauses": clauses,
    }
    _write_bundle(record, Path(args.out or "/tmp/stage20_verdict.json"))
    print(json.dumps(record["verdict"], indent=2, sort_keys=True))
    return 0 if go else 1


def _merge_base_guard() -> None:
    """P5: the ADR's first commit must precede the I4 record commit."""
    adr_commit = (
        subprocess.run(
            [
                "git",
                "-C",
                str(_REPO_ROOT),
                "log",
                "--diff-filter=A",
                "--format=%H",
                "--",
                str(_ADR),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        .stdout.strip()
        .splitlines()
    )
    i4_record = _REPO_ROOT / "data/vv/stage20_i4_calibration.json"
    if not i4_record.exists():
        raise SystemExit(
            "P5/P4: no I4 record exists (data/vv/stage20_i4_calibration.json) — the "
            "pre-flight has not run and nothing may be gated"
        )
    i4_commit = (
        subprocess.run(
            [
                "git",
                "-C",
                str(_REPO_ROOT),
                "log",
                "--diff-filter=A",
                "--format=%H",
                "--",
                str(i4_record),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        .stdout.strip()
        .splitlines()
    )
    if not adr_commit or not i4_commit:
        raise SystemExit("P5: cannot resolve the ADR or I4 record commit — refusing a gated run")
    check = subprocess.run(
        [
            "git",
            "-C",
            str(_REPO_ROOT),
            "merge-base",
            "--is-ancestor",
            adr_commit[-1],
            i4_commit[-1],
        ],
        check=False,
    )
    if check.returncode != 0:
        raise SystemExit(
            "P5: git merge-base --is-ancestor says the ADR's first commit does not "
            "precede the I4 record — the pre-registration ordering is broken"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="aero-dev")
    parser.add_argument("--timeout", type=int, default=PROBE_CEILING_S)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--host-nfs-root", type=Path, default=None)
    parser.add_argument("--remote-nfs-root", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--probe", nargs=2, metavar=("ARM", "RUNG"))
    parser.add_argument("--probe-dt", type=float, default=PROBE_DT_S)
    parser.add_argument("--probe-windows", type=int, default=PROBE_N_WINDOWS)
    parser.add_argument("--collect-probe", type=Path)
    parser.add_argument("--collect-cost", type=Path)
    parser.add_argument("--concurrent-with", nargs="*", default=None)
    parser.add_argument("--submit", choices=sorted(ARMS))
    parser.add_argument("--status", type=Path)
    parser.add_argument("--collect", type=Path)
    parser.add_argument("--verdict", nargs=2, metavar=("FLEX_BUNDLE", "RIGID_BUNDLE"))
    args = parser.parse_args(argv)

    print(PREREGISTERED_GATE_BLOCK)

    if args.probe:
        arm, rung = args.probe
        if rung not in RUNGS:
            raise SystemExit(f"unknown rung {rung!r}; rungs are {sorted(RUNGS)}")
        max_time = args.probe_windows * args.probe_dt
        _prepare_and_submit(
            args,
            arm=arm,
            rung=rung,
            time_window_size=args.probe_dt,
            max_time=max_time,
            gated_intent=False,
            label="probe",
        )
        return 0
    if args.collect_probe:
        return _collect_probe(args)
    if args.collect_cost:
        return _collect_cost(args)
    if args.submit:
        if GATED_TIME_WINDOW_S is None or GATED_MAX_TIME_S is None:
            raise SystemExit(
                "refusing --submit: the gated sentinels are None (ADR-039 B2 is pending "
                "its I4 record); run the pre-flight first"
            )
        _merge_base_guard()
        assert is_gated_configuration(
            rung=GATED_RUNG, time_window_size=GATED_TIME_WINDOW_S, max_time=GATED_MAX_TIME_S
        )
        _prepare_and_submit(
            args,
            arm=args.submit,
            rung=GATED_RUNG,
            time_window_size=GATED_TIME_WINDOW_S,
            max_time=GATED_MAX_TIME_S,
            gated_intent=True,
            label="wave1",
        )
        return 0
    if args.status:
        submission = _submission(args.status)
        result = _run_long("status", f"root@{submission['host']}", submission["session"])
        print(result.stdout.strip() or result.stderr.strip())
        return result.returncode
    if args.collect:
        return _collect_arm(args)
    if args.verdict:
        return _verdict(args)
    parser.error(
        "choose a mode: --probe / --collect-probe / --collect-cost / --submit / "
        "--status / --collect / --verdict"
    )


if __name__ == "__main__":
    raise SystemExit(main())
