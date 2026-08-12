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
import math
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import numpy as np  # noqa: E402
from aero.adapters._base import CaseDir  # noqa: E402
from aero.adapters.openfoam.force_io import read_force_history  # noqa: E402
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
from aero.adapters.precice.logs import find_iterations_logs, read_iterations_log  # noqa: E402
from aero.adapters.precice.schedule import (  # noqa: E402
    common_windows,
    select_windows,
    window_indices,
)
from aero.adapters.precice.solver import PreciceCoupledSolver  # noqa: E402
from aero.orchestration.local_ssh import LocalSSHExecutor  # noqa: E402
from aero.provenance.four_fold import compute_provenance  # noqa: E402
from aero.vv.alignment import align_arms  # noqa: E402
from aero.vv.fsi.cost_model import attribute_step_cost  # noqa: E402
from aero.vv.fsi.hg2007_flexible_foil import (  # noqa: E402
    ARMS,
    FREQUENCY_HZ,
    GATED_040_MAX_TIME_S,
    GATED_040_MPI_RANKS,
    GATED_040_NUMERICS_LABEL,
    GATED_040_TIME_WINDOW_S,
    GATED_MAX_TIME_S,
    GATED_RUNG,
    GATED_TIME_WINDOW_S,
    NUMERICS_STACKS,
    RUNGS,
    evaluate_predicates,
    hg2007_case_spec,
    is_gated_configuration,
    is_gated_configuration_040,
)
from aero.vv.fsi.hg2007_readout import (  # noqa: E402
    FLUID_STAMP,
    ArmReadout,
    read_arm,
)
from aero.vv.fsi.preflight import signal_drift_reports  # noqa: E402
from aero.vv.paired_difference import (  # noqa: E402
    paired_delta_uncertainty,
    paired_delta_uncertainty_from_samples,
)
from numpy.typing import NDArray  # noqa: E402

_ADR = _REPO_ROOT / "docs/adrs/ADR-039-hg2007-flexible-foil-gate-preregistration.md"
_BEGIN = "<!-- GATE-BLOCK:BEGIN -->"
_END = "<!-- GATE-BLOCK:END -->"

#: ADR-040 is a SECOND source of record, with its own markers, so the two blocks can
#: never be extracted from each other by accident.
_ADR_040 = _REPO_ROOT / "docs/adrs/ADR-040-campaign-numerics-re-preregistration.md"
_BEGIN_040 = "<!-- GATE-BLOCK-040:BEGIN -->"
_END_040 = "<!-- GATE-BLOCK-040:END -->"

#: The candidate probe dt (ADR-039 I7) — exactly representable, and the probe max-time
#: is an exact multiple so the authored-consistency validator accepts it.
PROBE_DT_S = 3.5e-4
PROBE_N_WINDOWS = 4350  # 1.5225 s: one (1-cos) ramp cycle + half a settled cycle
PROBE_CEILING_S = 43200  # ADR-039 B1: per-submission ceiling

#: ADR-040 B0: the probe ceiling N3 runs under. It cannot be B1, because B1 is an OUTPUT
#: of N3 — and ADR-039's B1 was never satisfiable anyway (ADR-040 B1 carries the
#: arithmetic). 72 h covers N3's 76090 windows at the pessimistic end of the projection.
PROBE_CEILING_040_S = 259200


def _extract_fenced_block(text: str, *, begin: str, end: str, source: Path) -> str:
    if begin not in text or end not in text:
        raise ValueError(f"{source}: no {begin} ... {end} gate block")
    inner = text.split(begin, 1)[1].split(end, 1)[0]
    fenced = inner.strip()
    if not (fenced.startswith("```text") and fenced.endswith("```")):
        raise ValueError(f"{source}: the gate block is not a ```text fence")
    return fenced.removeprefix("```text").removesuffix("```").strip("\n") + "\n"


def gate_block_from_adr(adr_path: Path = _ADR) -> str:
    """The gate block exactly as ADR-039 states it, with one trailing newline."""
    return _extract_fenced_block(
        adr_path.read_text(encoding="utf-8"), begin=_BEGIN, end=_END, source=adr_path
    )


def gate_block_040_from_adr(adr_path: Path = _ADR_040) -> str:
    """The gate block exactly as ADR-040 states it, with one trailing newline."""
    return _extract_fenced_block(
        adr_path.read_text(encoding="utf-8"), begin=_BEGIN_040, end=_END_040, source=adr_path
    )


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


PREREGISTERED_GATE_BLOCK_040 = """\
THE ADR-040 GATE BLOCK (ADR-040 is the source of record for the campaign numerics, the
parallel seam and the budget; the campaign driver's PREREGISTERED_GATE_BLOCK_040 is the
operational copy, embedded in every ADR-040 bundle beside ADR-039's; required unit tests
assert byte-identity, shape and marker state. ADR-039's block is NOT touched and is
digest-pinned by test_adr039_gate_block_digest.py)

U - what ADR-039 carries over UNCHANGED, clause by clause (ADR-039 remains the
  pre-registration of record for everything not named in N, L, Q or BUDGET below; where
  a clause is re-run rather than cited, it is re-run against the SAME criterion)
  U0 why changing anything is admissible at all: NO GATED CAMPAIGN EVER RAN. The only
     thing this stage has ever seen from the pre-registered configuration is a COST -
     217 and 123 projected days against a 14-day ceiling - and never a RESULT. ADR-039's
     FORBIDDEN list binds changes made after a campaign, when a band could be moved
     towards a number already seen; its own P4 mechanism (sentinels None, gated DERIVED)
     is what kept that from happening. Everything below is chosen against measured COSTS
     and refuted HYPOTHESES, with every fidelity band untouched.
  U1 P1 P2 P3 P4 P5 unchanged. P1's SIF pins, the adapter commit and the roster contract
     are identical; the only difference is that the fluid participant now runs under
     mpirun (L3). P4's derivation gains two required inputs and is otherwise the same
     mechanism - see L5.
  U2 C1 C2 C3 C4 C5 C6 unchanged, and C1 is FROZEN in particular: parallel-implicit,
     max-iterations 50, relative convergence 5e-3 on both Displacement and Force,
     IQN-ILS with QR2 filter limit 1e-2, initial-relaxation 0.5, max-used-iterations 100,
     time-windows-reused 15. N4 below names a lever that lives inside C1. It is REPORTED
     and NOT acted on, because acting on it is what a frozen clause forbids.
  U3 I1 I3 I4 I5 I6 I7 I8 I9 unchanged as clauses. I1 I3 I8 I9 are CITED from their
     existing data/vv records and never re-run - none of them is a function of the linear
     solver. I4 I5 I7 are re-run under the ADR-040 stack, against the same criteria,
     because a rate, a mesh-motion trace and a Courant number are all properties of the
     numerics that produced them.
  U4 R1 R2 R3 unchanged. The reference of record stays hg2007_recomputed.csv and no
     reference row moves.
  U5 K1 K2 K3 unchanged, including K1's window-scoped range and K3's repeat-cadence
     classification, which RAISES on any repeat the iterations log does not account for.
  U6 S1 S2 S3 S4 S5 unchanged: the prescribed period T = 1.0145 s, the unconditional 3/f
     discard, the fundamental-anchored convergence test, at least 20 settled cycles on
     the paired rung and 10 on the GCI rungs, the last-checkpoint rule, and the
     cumulative per-signal bound.
  U7 A1 A2 A3 A4 A5 unchanged. A4 - matched numerics by construction - now additionally
     requires that both arms share the numerics label and the fluid rank count, which L5
     makes structural rather than a matter of discipline.
  U8 D0 D1 D2 D3 D4 D5 D6 D7 D8 D9 D10 unchanged, every band verbatim: 25 %, 25 %, 40 %,
     25 %, 25 %, (no band), (no band), (no band), 2 deg, (no band), 2 %. NO BAND MOVES,
     the gated set is the same set, D9 stays reported-only and D10 stays gated. The
     ordered (clause, band) parity against CLAUSE_BANDS is ADR-039's test and stays green.
  U9 M1 M2 M3 M4 unchanged, and the X diagnostics list is unchanged.
  U10 ADR-039's VERDICT line IS the stage verdict, verbatim and clause by clause.
     ADR-040 introduces no gated physics clause and cannot change the outcome of one.
  U11 ADR-039 B3 and B4 carry over; ADR-039's contingencies N1 N2 N3 N4 carry over
     verbatim. ADR-039 B1 and B2 are SUPERSEDED by the BUDGET section below, and
     ADR-039's <<B2-PENDING-I4>> marker STANDS UNFILLED PERMANENTLY: the campaign it
     would have sized was measured infeasible and will never run, so its sentinels stay
     None and its --submit mode refuses forever. That is a state, not an oversight, and
     test_adr039_b2_marker_state.py keeps it true.

N - the campaign numerics, re-pre-registered (measured in the data/vv records
  stage20_i10_cost_split.json, stage20_n2_screening.json and
  stage20_n4_deforming_screen.json; every rejected lever below is rejected on a
  measurement rather than on an argument)
  N1 the fluid linear-solver stack, by token, label adr040-candidate: p solver GAMG;
     p smoother DICGaussSeidel; p tolerance 1e-6; p relTol 0.01; pcorr tolerance 0.02;
     no GAMG controls; nOuterCorrectors 1; nCorrectors 2; nNonOrthogonalCorrectors 1.
     Measured 3.73x serial static and 4.36x on a mesh that moves, against the ADR-039
     stack. The single token DICGaussSeidel is worth 2.22x of that and drops GAMG
     iterations per step from 302 to 51: the coarse-grid correction was not working
     under a plain Gauss-Seidel smoother at cell aspect ratios near 310.
     nOuterCorrectors 1 is a DECK change, not a knob - OpenFOAM then tags every inner
     iteration final and demands cellDisplacementFinal, and a deck carrying only
     cellDisplacement dies with FOAM FATAL IO ERROR on the first time step.
  N2 what is deliberately NOT changed, each refuted by measurement: cacheAgglomeration
     no leaves the pressure solve at 41.3 iterations per solve against 40.3 with the
     cache on - no reduction at all - and costs 6.8 percent, 21.4 percent on this stack;
     pinning the ENTIRE farfield pressure, the strongest and deliberately
     over-constrained form of the pressure-reference fix, is worth 3 percent, inside
     scatter, so NO CAMPAIGN BOUNDARY CONDITION CHANGES; forces1 write scheduling and
     fluid subcycling are both bounded away by I10's 99.42 percent fluid-CPU share
     (0.58 percent and about 6.6 percent respectively); PCG+DIC is 1.07x and stays
     rejected; the time scheme stays Euler per I8; dt stays the candidate 2e-5 s subject
     to W5.
  N3 THE COUPLED CONFIRMATION - the only measurement in this stage permitted to size B2.
     Both arms concurrently at the gated rung, 4 fluid ranks each (L3), the N1 stack,
     dt 2e-5 s, 76090 windows = 1.5218 s. The (1-cos) ramp ends at window 50725, so this
     covers 25364 post-ramp windows = one full half-stroke, over which the plunge speed
     runs 0 -> peak -> 0 and the phase coverage of |v| is complete by symmetry.
     THE SIZING RATE IS THE POST-RAMP RATE, over a whole number of post-ramp
     quarter-cycles, and never wall_clock_s / windows_completed: two thirds of these
     windows sit inside the ramp at near-zero plunge and would understate the wave. A
     ramp-phase rate may not size; a fluid-only screen may not size; an uncontended run
     may not size.
  N4 REPORTED, NEVER ACTED ON - where the residual cost is. The campaign's pressure
     solve is permanently cold-started: under implicit coupling every iteration restores
     the window-start checkpoint, so the solve never inherits a converged iterate. The
     screen's own first five steps cost 78.2 iterations per p solve from uniform fields
     and decay to 40.3 by step five; the campaign's first five sit at 91.2 - the screen's
     STARTUP number, not its settled one - and never decay, running 113.0 over 2627
     solves. Four consistent signatures: present from the first solve, flat across
     position in the window (987 on iteration 1 against 977 on iteration 3), flat in
     time, and untouched by both refuted knobs. This is an ATTRIBUTION, not a
     confirmation - a fluid-only screen structurally cannot test it. The lever it implies
     is the per-iteration initial guess, which lives in C1, which is frozen (U2). If N3's
     measured rate lands far from the projection this is the first place to look, and
     closing it needs a NEW ADR, not a knob.
  N5 the caveats parallelism carries into every downstream number, stated so they are
     not rediscovered as anomalies: under mpirun OpenFOAM's ExecutionTime is RANK 0's
     CPU, not the aggregate, so I10's 99.42 percent bound does NOT transfer to a parallel
     run and the post-ramp rate is read from ClockTime; ClockTime prints at
     integer-second resolution, which is ample over a run of hours and useless over one
     of seconds; under decomposition time directories sit at processor*/<time>, so I4's
     disk accounting and its time-directory count are rank-aware or they read zero.

L - the live MPI ladder and the parallel seam (L1 and L2 already PASSED and are cited
  from data/vv/stage20_n2_screening.json; L3 is measured in
  data/vv/stage20_n4_deforming_screen.json)
  L1 PASSED: mpirun is REFUSED outright by OpenMPI when it runs as root, and works under
     the setpriv uid drop (4 ranks, Open MPI 4.1.6). So the seam is
     build_participant_command and never build_apptainer_exec(mpi_n=...), which would
     hoist mpirun outside the drop or emit mpirun -n 4 cd fluid-openfoam - a solver that
     runs SERIAL and exits 0.
  L2 PASSED: at 2, 4, 6 and 8 ranks postProcessing/forces1/0/force.dat lands in the CASE
     ROOT, never under processor*/, so the readout needs no change under decomposition.
  L3 the fluid rank count is 4 PER ARM, pre-registered with no free knob, 10 of
     aero-dev's 16 cores with the two CalculiX participants. Measured in the wave-1 shape
     - two arms concurrently, moving mesh, binding on the SLOWER arm because the wave is
     not done until both are: 4+4 gives 0.1655 s/step against 6+6's 0.1860 on 14 cores,
     medians over repeats. The uncontended moving-mesh ladder agrees and is sharper,
     pressure iterations per solve rising monotonically 5.6 / 9.2 / 11.4 / 18.4 / 36.1
     across 1 / 2 / 4 / 6 / 8 ranks - an iteration count is a far more robust witness
     than a wall clock on a shared box. The standing 6-rank decision came from an
     UNCONTENDED ladder on a STATIC mesh and is superseded.
  L4 decomposePar runs UNDER THE PARTICIPANT UID, not as root like blockMesh: pimpleFoam
     writes into processor*/ every time step and root-owned directories kill the run at
     t=0. The processor* count is COUNTED on the host and must equal the requested rank
     count before any submit - decomposePar exits 0 having fallen back to fewer
     subdomains, and that is a different configuration wearing this one's clothes.
  L5 gated is DERIVED by is_gated_configuration_040 from FIVE required inputs - rung,
     time-window-size, max-time, numerics label AND fluid rank count - never passed in.
     Two of those are new because without them a run at the right dt with the wrong
     numerics, or at the wrong rank count, would claim the gated verdict. ADR-039's
     is_gated_configuration is left untouched and returns False permanently (U11).
  L6 the L-SMOKE: a short coupled run through the real driver path, both arms at 4+4,
     must PASS before N3 is submitted - processor* count correct on both arms, mpirun
     inside the uid drop in the staged supervisor, both participants exit 0, coupling
     converged, force.dat in the case root. Two minutes to de-risk two days.

Q - equivalence against the ADR-039-numerics baseline (the band and the REJECTION
  outcome are fixed here, before the probe runs; the baseline side costs nothing because
  the surviving I4 bytes are on disk)
  Q1 500 coupled windows at the I4 shape, both arms concurrently, under the N1 stack at
     4+4 ranks, against the surviving ADR-039-numerics I4 runs
     hg2007_flexible_foil-20260810-144742 and hg2007_rigid_foil-20260810-144747. Three
     pre-registered comparisons, all of which must hold: (a) the span-mean streamwise
     interface force per arm within 2 percent of the baseline's span-mean; (b) the
     per-window trace within 5 percent of the baseline trace's peak-to-peak amplitude in
     maximum absolute deviation - an absolute band scaled by a MEASURED amplitude,
     because a relative bound is undefined at a zero crossing; (c) the flexible-minus
     -rigid difference of the span-means within 5 percent of the baseline difference,
     stated separately so that a common-mode shift is not read as an increment failure
     and an anti-symmetric one is not read as a pass.
  Q2 what Q1 does NOT establish, stated rather than left to be assumed. The I4 shape
     sits inside the ramp: over its whole 0.01 s the foil moved 2.6e-07 m, 0.006 of ONE
     wall cell. So Q1 certifies that the stack reproduces the ADR-039 numerics' forces IN
     THAT REGIME, not post-ramp. And it compares the configuration AS DELIVERED - N1's
     numerics and the 4-way decomposition together - so a rejection does not localize;
     the declared localizing follow-up is a serial run at the N1 numerics.

VERDICT: ADR-040 has NO verdict of its own over the physics. ADR-039's clause-by-clause
VERDICT line stands verbatim and is the only verdict this stage will ever take (U10).
ADR-040's own outcomes are four, each a recorded result either way: L6 passes or N3 is
not submitted; Q1 accepts or the N1 stack is inadmissible (W4); N3 measures a post-ramp
rate or FAILS (W3); and B2 is then either filled from that rate through the committed
sizing rule or the stage records a budget NO-GO. A budget NO-GO is a result. No band is
relaxed under any circumstance, and no number below is chosen after seeing a rate.

BUDGET (pre-declared): aero-dev only, no cloud spend, 4 fluid ranks per arm, two waves.
  B0 the ADR-040 PROBE ceiling: 259200 s (72 h) per submission, 432000 s (5 d) total,
     covering L6, Q1 and N3. This clause exists because N3 cannot be ceilinged by B1:
     B1 is an OUTPUT of N3. At the pessimistic end of the projection N3's 76090 windows
     cost 59.2 h, so 72 h carries about 22 percent headroom and still clears the ramp
     alone at up to 5.1 s/window.
  B1 pre-flight ceiling: <<B1-PENDING-N3>>
     ADR-039's B1 - 43200 s per submission - was NEVER SATISFIABLE, and saying so is part
     of the record. I7 must reach the post-ramp window, which needs at least 50725
     windows; against 43200 s that demands 0.85 s/window, TIGHTER than the 1.037
     s/window B2 itself needed for 20 settled cycles in 14 days. A pre-flight ceiling
     that binds harder than the campaign it is a pre-flight for cannot be met by any run
     that would justify the campaign. The replacement is an OUTPUT of N3's measured
     post-ramp rate, re-derived by a required test, and is filled in the same commit as
     the N3 record.
  B2 gated campaign: <<B2-PENDING-ADR040>>
     The sizing RULE is pre-registered now and the numbers are an output of the N3 record
     through aero/vv/fsi/hg2007_sizing.py:size_gated_campaign_040, re-derived by a
     required test. The gated rung is mid, both arms; the time-window-size is the
     Co-passing probe's dt verbatim, never scaled from a measurement at another dt;
     max-time is the smallest exact multiple of dt covering the S2 discard plus 20
     settled cycles, bumped to the first value for which n*dt survives a .13e round trip;
     the projection uses N3's CONTENDED POST-RAMP seconds-per-window; dt is FIXED across
     all three rungs so temporal error is common-mode (I8), which is why I7 must also
     pass on the fine rung.
  B3 per-wave ceiling: <<B3-PENDING-CEILING>>
     ADR-039's 14-day per-wave ceiling is MEASURED out of reach at any settled-cycle
     count: 20 cycles need 1.037 s/window and 10 need 1.834, against a projection of
     about 2.00. The DECISION RULE is pre-registered here and only the number is pending:
     the operator is brought N3's coupled, contended, post-ramp rate and approves the
     SMALLEST ceiling that fits 20 settled cycles at that rate, and the approval is taken
     BEFORE B2 is filled - so the ceiling is chosen against a measured rate and not
     against a projected campaign length that someone wants to fit.
  B4 reaching a ceiling is a RECORDED OUTCOME, not a failure, exactly as in ADR-039. The
     declared last resorts, in order: cut settled cycles (never below 10), then a budget
     NO-GO. If S3 cannot be satisfied within the ceiling the verdict is NO-GO on periodic
     steady state - never a re-run with a hand-picked window.

CONTINGENCIES - MECHANISM (allowed, declared in advance) vs GATE (forbidden); items are
  W-prefixed because N is a numerics family here AND ADR-039's own contingencies are
  N-prefixed, so every cross-ADR reference in this document is qualified (ADR-039 N3)
  W1 if the L-smoke (L6) fails, N3 is NOT submitted. The seam is fixed and the smoke
     re-run; a failed smoke is recorded and never bypassed, because the thing it proves
     is the thing a two-day run would otherwise discover at hour 40.
  W2 if the processor* count does not equal the requested rank count, the run is
     REFUSED, before submit. There is no fallback rank count: L3 pre-registers one.
  W3 if N3 reaches B0 before completing one whole post-ramp quarter-cycle, N3 FAILS,
     B2 stays pending and the record says so. If it reaches B0 having completed at least
     one whole post-ramp quarter-cycle, the rate is taken over the largest whole number
     of post-ramp quarter-cycles completed and the record states the phase coverage.
  W4 if Q1 rejects, the N1 stack is INADMISSIBLE and N3's rate may not size B2 even if
     N3 itself succeeded. The declared alternatives, in order: re-run the campaign
     confirmation on ADR-039's numerics under the B3 ceiling, or record a budget NO-GO.
     The band is not widened and the comparison is not re-chosen.
  W5 the CONDITIONAL dt re-probe, pre-authorised here and nowhere else: if N3's measured
     post-ramp max Courant is at most 0.4, ONE probe at the next larger round-tripping dt
     is permitted, and the campaign dt is the largest probed dt whose post-ramp max
     Courant is at most 0.8. Any dt that is not itself a passing probe's dt is refused,
     and n*dt must survive a .13e round trip or the CalculiX field width rejects the deck.
  W6 if a wave-1 solve ends participant-died, ADR-039 N3 applies unchanged: one
     resubmission, both arms, new run ids, both bundles shipped, and a second death is a
     NO-GO on infrastructure.
  FORBIDDEN: everything ADR-039's FORBIDDEN list names - any D band, any convergence
  limit, max-iterations, the S2 discard, the settled-cycle minima, the analysis window,
  the reference row, M3's motion margin - and, after the N3 record exists: the N1 stack,
  the L3 rank count, the definition of the sizing rate, and the Q1 bands. Any of these
  requires a NEW ADR, and the original verdict stands on the record.
"""


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _write_bundle(record: dict[str, Any], out: Path) -> None:
    """Write a bundle carrying BOTH pre-registrations, additively.

    ``adr`` and ``preregistered_gate_block`` keep their ADR-039 meaning and their
    ``setdefault`` semantics, so the three committed records that embed the block and are
    compared against the driver constant in CI stay exactly as they are. ADR-040's block
    rides alongside under its own key, because a bundle produced under the ADR-040
    numerics is only self-describing if it carries the document that pre-registered them.
    """
    record.setdefault("preregistered_gate_block", PREREGISTERED_GATE_BLOCK)
    record.setdefault("preregistered_gate_block_040", PREREGISTERED_GATE_BLOCK_040)
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


SUBMISSION_SCHEMA = "stage20-submission-v2"
_SUPERSEDED_SCHEMA = "stage20-submission-v1"


def _submission(path: Path) -> dict[str, Any]:
    """Read a submission, refusing the superseded schema by name.

    v1's ``spec_knobs`` carried five keys. ADR-040 adds ``numerics_label`` and
    ``mpi_ranks``, and ``_reattach`` passes the whole dict to ``hg2007_case_spec`` to
    rebuild the spec and re-derive its digest. Handed a v1 record it would rebuild an
    ADR-039-numerics serial spec, get a digest that does not match, and report "the code
    moved under a live campaign" -- true, but the wrong diagnosis and the wrong action.
    So the refusal names the bump instead.
    """
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    schema = data.get("schema")
    if schema == _SUPERSEDED_SCHEMA:
        raise SystemExit(
            f"{path} is a {_SUPERSEDED_SCHEMA} record and the submission schema is now "
            f"{SUBMISSION_SCHEMA}. v2 carries numerics_label and mpi_ranks in spec_knobs, "
            "which _reattach must pass to hg2007_case_spec or the digest check compares a "
            "spec that is not the one that ran. A v1 submission describes a configuration "
            "this driver can no longer build; re-submit rather than editing the record."
        )
    if schema != SUBMISSION_SCHEMA:
        raise SystemExit(f"{path} is not a {SUBMISSION_SCHEMA} file (schema={schema!r})")
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
    numerics_label: str = "adr039-baseline",
    mpi_ranks: int = 1,
) -> Path:
    """prepare -> mesh (sync) -> [decompose] -> stage -> submit detached -> persist."""
    spec = hg2007_case_spec(
        arm=arm,  # type: ignore[arg-type]
        rung=rung,
        time_window_size=time_window_size,
        max_time=max_time,
        wall_clock_ceiling_s=args.timeout,
        numerics_label=numerics_label,
        mpi_ranks=mpi_ranks,
    )
    if gated_intent and not spec.gated:
        raise SystemExit(
            "refusing a gated submit: the gate predicate returned False — either the "
            "sentinels are unfilled or this is not the gated configuration (rung, "
            "time-window-size, max-time, numerics label, rank count)"
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

    decomposition = None
    if mpi_ranks > 1:
        # ADR-040 L4/W2: BEFORE the submit, and the processor* count is counted rather
        # than trusted. decomposePar exits 0 having fallen back to fewer subdomains.
        print(f"decompose: decomposePar -force into {mpi_ranks} subdomains (sync, as uid)")
        report = solver.decompose(case_dir, executor, ranks=mpi_ranks)
        if not report.ok:
            raise SystemExit(f"NO-GO (ADR-040 W2: decomposition refused): {report.failure}")
        decomposition = json.loads(report.model_dump_json())

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
        "schema": SUBMISSION_SCHEMA,
        "adr": "ADR-039" if numerics_label == "adr039-baseline" and mpi_ranks == 1 else "ADR-040",
        "label": label,
        "arm": arm,
        "rung": rung,
        "decomposition": decomposition,
        "run_id": case_dir.run_id,
        "session": staged.session,
        "host": args.host,
        "ssh_user": "root",
        # EVERY argument hg2007_case_spec needs to rebuild this exact spec. A knob that
        # does not ride here is a knob that makes _reattach refuse every collect.
        "spec_knobs": {
            "arm": arm,
            "rung": rung,
            "time_window_size": time_window_size,
            "max_time": max_time,
            "wall_clock_ceiling_s": args.timeout,
            "numerics_label": numerics_label,
            "mpi_ranks": mpi_ranks,
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

    spec = hg2007_case_spec(**submission["spec_knobs"])
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
        # From the SUBMISSION, not defaulted: an ADR-040 probe's bundle must not claim to
        # be an ADR-039 record just because _write_bundle's setdefault says so.
        "adr": submission.get("adr", "ADR-039"),
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
    # RANK-AWARE (ADR-040 N5). Under decomposition OpenFOAM writes time directories to
    # processor*/<time>, one level DEEPER than the serial layout, so the maxdepth-3 form
    # this replaced counted zero on a parallel run and the F4 disk projection -- the
    # thing standing between the wave and a full NFS -- silently read as no growth.
    time_dirs = executor.run(
        f"find {remote_case_root} -maxdepth 4 -type d -regex '.*/[0-9.]+' | wc -l"
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
    if covers_post_ramp:
        record["n3"] = _n3_block(
            fluid_log,
            submission=submission,
            status_stopped_by=status.stopped_by,
            windows_completed=int(fluid.get("n_windows", 0)),
            windows_requested=windows_requested,
            period_s=period,
            max_courant_post_ramp=record["i7"]["max_courant_post_ramp"],
            du_bytes=record["i4"]["du_bytes"],
            time_dir_count=record["i4"]["time_dir_count"],
            concurrent_with=list(args.concurrent_with or ()),
        )

    _write_bundle(record, Path(args.out or "/tmp/stage20_probe_collected.json"))
    ok = bool(record["i7"]["passed"]) and status.stopped_by == "all-exited"
    # `passed` and `max_courant_post_ramp` are BOTH None for a run inside the ramp, which
    # is the state both committed I4 bundles are in; `f"{None:.4f}"` raised TypeError
    # AFTER the bundle was written, so the record survived and the mode reported a crash.
    measured = record["i7"]["max_courant_post_ramp"]
    shown = "not measured (run did not reach the post-ramp window)"
    if measured is not None:
        shown = f"{measured:.4f}"
    print(
        f"I7 max post-ramp Courant: {shown} (passed={record['i7']['passed']}); "
        f"stopped_by={status.stopped_by}"
    )
    if "n3" in record:
        n3 = record["n3"]
        print(
            f"N3 post-ramp rate: {n3['post_ramp_seconds_per_window']} s/window over "
            f"{n3['post_ramp_windows_measured']} windows "
            f"({n3['post_ramp_quarter_cycles']} quarter-cycle(s))"
        )
    return 0 if ok else 1


def _n3_block(
    fluid_log: Path,
    *,
    submission: dict[str, Any],
    status_stopped_by: str,
    windows_completed: int,
    windows_requested: int,
    period_s: float,
    max_courant_post_ramp: float | None,
    du_bytes: int,
    time_dir_count: int,
    concurrent_with: list[str],
) -> dict[str, Any]:
    """ADR-040 N3: the POST-RAMP rate, over a whole number of quarter-cycles.

    Read from the fluid log's cumulative ``ClockTime`` rather than from
    ``status.wall_clock_s / windows``, for two reasons that are both measurements.

    ``wall_clock_s / windows_completed`` is what ADR-039 used, and under the ``(1-cos)``
    ramp roughly two thirds of an N3 run sits at near-zero plunge -- averaging that in
    produces a comfortable rate and an unaffordable campaign.

    ``ExecutionTime`` is not usable either: under ``mpirun`` OpenFOAM reports RANK 0's
    CPU, not the aggregate (ADR-040 N5). ``ClockTime`` is wall clock and is correct at any
    rank count; it prints at integer-second resolution, which over a run of hours is
    ample.

    The span is trimmed DOWN to whole quarter-cycles rather than rounded to the nearest,
    so a ceiling stop mid-stroke yields a shorter honest measurement instead of a longer
    phase-weighted one.
    """
    dt = float(submission["spec_knobs"]["time_window_size"])
    ramp_windows = math.ceil(period_s / dt)
    quarter_windows = max(1, round(period_s / 4.0 / dt))

    cost = read_fluid_cost_history(fluid_log)
    # The log's steps are per fluid STEP-SOLVE (one per coupling iteration), so the
    # window a step belongs to is read off its own time, never off its index.
    courant = read_courant_history(fluid_log)
    if len(courant.t) != len(cost.steps):
        raise SystemExit(
            f"{fluid_log}: {len(courant.t)} Courant lines against {len(cost.steps)} "
            "ExecutionTime lines — the two per-step series must pair one to one, and a "
            "mismatch means the log was truncated mid-step"
        )

    completed_post_ramp = max(0, windows_completed - ramp_windows)
    measured_windows = (completed_post_ramp // quarter_windows) * quarter_windows
    block: dict[str, Any] = {
        "arm": submission["arm"],
        "rung": submission["rung"],
        "dt": dt,
        "period_s": period_s,
        "numerics_label": submission["spec_knobs"]["numerics_label"],
        "mpi_ranks": submission["spec_knobs"]["mpi_ranks"],
        "windows_requested": windows_requested,
        "windows_completed": windows_completed,
        "stopped_by": status_stopped_by,
        "ramp_windows": ramp_windows,
        "quarter_cycle_windows": quarter_windows,
        "post_ramp_windows_completed": completed_post_ramp,
        "post_ramp_windows_measured": measured_windows,
        "post_ramp_quarter_cycles": measured_windows // quarter_windows,
        "max_courant_post_ramp": max_courant_post_ramp,
        "time_dir_count": time_dir_count,
        "du_bytes": du_bytes,
        "concurrent_with": concurrent_with,
        "rate_source": "fluid log ClockTime (NOT ExecutionTime: rank 0's CPU under mpirun)",
    }
    if measured_windows == 0:
        block["post_ramp_wall_clock_s"] = 0.0
        block["post_ramp_seconds_per_window"] = None
        block["why_no_rate"] = (
            f"{completed_post_ramp} post-ramp window(s) is less than one quarter-cycle "
            f"({quarter_windows}); a rate over a fractional quarter-cycle is "
            "phase-weighted and ADR-040 W3 refuses it"
        )
        return block

    t_start = ramp_windows * dt
    t_end = (ramp_windows + measured_windows) * dt
    half = 0.5 * dt
    clocks = [
        step.clock_time_s
        for step, t in zip(cost.steps, courant.t, strict=True)
        if t_start - half <= t <= t_end + half
    ]
    if len(clocks) < 2:
        raise SystemExit(
            f"{fluid_log}: fewer than two step records inside the post-ramp span "
            f"[{t_start}, {t_end}] — no wall clock can be differenced over it"
        )
    wall = float(clocks[-1] - clocks[0])
    block["post_ramp_wall_clock_s"] = wall
    block["post_ramp_step_solves_measured"] = len(clocks)
    block["post_ramp_seconds_per_window"] = wall / measured_windows
    return block


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


#: ADR-040 Q1's three pre-registered comparisons, fixed in the ADR before the probe ran.
_Q1_SPAN_MEAN_BAND = 0.02
_Q1_TRACE_BAND = 0.05
_Q1_INCREMENT_BAND = 0.05

#: The surviving ADR-039-numerics runs Q1 compares against. Named here rather than
#: discovered, because "whichever run is in that directory" is not a baseline.
_Q1_BASELINE_RUNS = {
    "flexible": "hg2007_flexible_foil-20260810-144742",
    "rigid": "hg2007_rigid_foil-20260810-144747",
}


def _q1_series(case_root: Path) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """One run's per-window streamwise interface force, on the coupling's window grid.

    Reads through the window-index join rather than off raw times, for the reason
    `precice.schedule` exists: the two records do not share a float axis. Returns the
    window indices and the CONVERGED streamwise total force for each.
    """
    case = next(case_root.glob("hg2007-*-foil"))
    fluid_dir = case / "fluid-openfoam"
    report = read_iterations_log(
        find_iterations_logs(case)["Fluid"], participant="Fluid", max_iterations_configured=50
    )
    forces = read_force_history(fluid_dir / "postProcessing/forces1/0/force.dat", repeats="last")
    dt = float(np.median(np.diff(np.unique(forces.t))))
    index = window_indices(forces.t, time_window_size=dt, stamp=FLUID_STAMP, label=str(case_root))
    fx = (forces.pressure + forces.viscous)[:, 0]
    # Drop the trailing stamp, which maps to a window that does not exist.
    keep = index <= report.n_windows
    return index[keep], fx[keep]


def _record_q1(args: argparse.Namespace) -> int:
    """ADR-040 Q1: does the candidate stack reproduce the ADR-039 numerics' forces?

    Compares the two ADR-040 probes against the two surviving ADR-039-numerics I4 runs,
    window for window. The baseline side costs nothing -- its bytes are still on NFS -- and
    the bands and the rejection outcome were fixed in ADR-040 before either probe ran.

    Q2's limit is carried in the record, not left to a reader: the I4 shape sits inside the
    ramp, where the foil moved 0.006 of one wall cell, and the comparison is of the
    configuration AS DELIVERED (numerics AND the 4-way decomposition together), so a
    rejection does not localize.
    """
    arms: dict[str, Any] = {}
    span_means: dict[str, dict[str, float]] = {}
    for arm, path in (("flexible", args.record_q1[0]), ("rigid", args.record_q1[1])):
        submission = _submission(Path(path))
        if submission["arm"] != arm:
            raise SystemExit(f"{path} is the {submission['arm']!r} arm, expected {arm!r}")
        if submission["spec_knobs"]["numerics_label"] != "adr040-candidate":
            raise SystemExit(
                f"{path} ran on {submission['spec_knobs']['numerics_label']!r}; Q1 compares "
                "the adr040-candidate stack against the ADR-039 baseline"
            )
        candidate_root = Path(submission["case_host_path"]) / CASE_ROOT_DIRNAME
        baseline_root = Path("/mnt/aero-nfs/runs") / _Q1_BASELINE_RUNS[arm] / CASE_ROOT_DIRNAME
        if not baseline_root.is_dir():
            raise SystemExit(
                f"{baseline_root} is gone — Q1's baseline is the surviving ADR-039-numerics "
                "I4 run, and a comparison against a run that no longer exists cannot be "
                "re-checked"
            )
        c_idx, c_fx = _q1_series(candidate_root)
        b_idx, b_fx = _q1_series(baseline_root)
        windows = common_windows({"candidate": c_idx, "baseline": b_idx})
        c = c_fx[select_windows(c_idx, windows, label="candidate")]
        b = b_fx[select_windows(b_idx, windows, label="baseline")]

        span_mean_c, span_mean_b = float(np.mean(c)), float(np.mean(b))
        amplitude = float(np.max(b) - np.min(b))
        max_dev = float(np.max(np.abs(c - b)))
        span_means[arm] = {"candidate": span_mean_c, "baseline": span_mean_b}
        arms[arm] = {
            "candidate_run_id": submission["run_id"],
            "baseline_run_id": _Q1_BASELINE_RUNS[arm],
            "n_windows_compared": int(windows.size),
            "span_mean_fx_candidate": span_mean_c,
            "span_mean_fx_baseline": span_mean_b,
            "span_mean_relative_difference": abs(span_mean_c - span_mean_b)
            / max(abs(span_mean_b), 1e-300),
            "baseline_trace_peak_to_peak": amplitude,
            "max_absolute_deviation": max_dev,
            "trace_deviation_over_amplitude": max_dev / max(amplitude, 1e-300),
        }
        arms[arm]["q1a_span_mean_within_band"] = bool(
            arms[arm]["span_mean_relative_difference"] <= _Q1_SPAN_MEAN_BAND
        )
        arms[arm]["q1b_trace_within_band"] = bool(
            arms[arm]["trace_deviation_over_amplitude"] <= _Q1_TRACE_BAND
        )

    d_candidate = span_means["flexible"]["candidate"] - span_means["rigid"]["candidate"]
    d_baseline = span_means["flexible"]["baseline"] - span_means["rigid"]["baseline"]
    increment_rel = abs(d_candidate - d_baseline) / max(abs(d_baseline), 1e-300)
    clauses = {
        "Q1a_span_mean_per_arm": all(a["q1a_span_mean_within_band"] for a in arms.values()),
        "Q1b_trace_per_arm": all(a["q1b_trace_within_band"] for a in arms.values()),
        "Q1c_increment_of_span_means": bool(increment_rel <= _Q1_INCREMENT_BAND),
    }
    record: dict[str, Any] = {
        "adr": "ADR-040",
        "clause": "Q1-equivalence",
        "kind": "equivalence-probe",
        "gated": False,
        "started_at": _utc_now(),
        "bands": {
            "Q1a_span_mean": _Q1_SPAN_MEAN_BAND,
            "Q1b_trace_over_baseline_amplitude": _Q1_TRACE_BAND,
            "Q1c_increment_of_span_means": _Q1_INCREMENT_BAND,
            "note": "fixed in ADR-040 Q1 BEFORE either probe ran; not widened, ever",
        },
        "arms": arms,
        "increment": {
            "d_span_mean_candidate": d_candidate,
            "d_span_mean_baseline": d_baseline,
            "relative_difference": increment_rel,
            "why_separate": (
                "stated on its own so a common-mode shift is not read as an increment "
                "failure and an anti-symmetric one is not read as a pass"
            ),
        },
        "clauses": clauses,
        "accepted": all(clauses.values()),
        "q2_limits": (
            "The I4 shape sits INSIDE the ramp: over its whole 0.01 s the foil moved "
            "2.6e-07 m, 0.006 of ONE wall cell. So Q1 certifies that the stack reproduces "
            "the ADR-039 numerics' forces IN THAT REGIME, not post-ramp. And it compares "
            "the configuration AS DELIVERED - the N1 numerics and the 4-way decomposition "
            "together - so a rejection does not localize; the declared localizing "
            "follow-up is a serial run at the N1 numerics (ADR-040 Q2)."
        ),
        "rejection_outcome": (
            "ADR-040 W4: if Q1 rejects, the N1 stack is INADMISSIBLE and N3's rate may not "
            "size B2 even if N3 itself succeeded. The declared alternatives, in order: "
            "re-run the campaign confirmation on ADR-039's numerics under the B3 ceiling, "
            "or record a budget NO-GO. The band is not widened."
        ),
    }
    _write_bundle(record, Path(args.out or _REPO_ROOT / "data/vv/stage20_q1_equivalence.json"))
    for name, passed in sorted(clauses.items()):
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    for arm, a in sorted(arms.items()):
        print(
            f"  {arm}: span-mean rel {a['span_mean_relative_difference']:.4%}, "
            f"trace/amplitude {a['trace_deviation_over_amplitude']:.4%}, "
            f"{a['n_windows_compared']} windows"
        )
    print(f"  increment rel {increment_rel:.4%}")
    return 0 if record["accepted"] else 1


def _record_l6(args: argparse.Namespace) -> int:
    """ADR-040 L6: the parallel coupled smoke, recorded as evidence rather than an anecdote.

    Every clause below is read back off the run's own bytes -- the staged supervisor
    script, the case tree, the participant logs -- rather than asserted from what the
    driver believes it did. L1 and L2 were measured in session 9 on a FLUID-ONLY screen;
    re-reading them here is the first time either has been checked on the real coupled
    deck, which is the deck that has a second participant and a preCICE handshake in it.
    """
    submission = _submission(Path(args.record_l6))
    ranks = int(submission["spec_knobs"]["mpi_ranks"])
    if ranks < 2:
        raise SystemExit(
            f"{args.record_l6} ran at {ranks} rank(s) — the L-smoke exists to exercise the "
            "PARALLEL seam, and a serial run proves nothing about it"
        )
    case_root = Path(submission["case_host_path"]) / CASE_ROOT_DIRNAME
    supervisor = (case_root / "run-coupled.sh").read_text(encoding="utf-8")
    # The fluid directory comes from the SPEC, never from the run id's spelling.
    solver, case_dir, result = _reattach(args, submission)
    spec = case_dir.spec
    fluid_dir = case_root / spec.case_subdir / spec.fluid_participant_dir
    status = solver.coupled_status(result)

    mpi_element = f"mpirun -n {ranks} pimpleFoam -parallel"
    before_drop = supervisor.split("setpriv", 1)[0]
    processor_dirs = sorted(p.name for p in fluid_dir.glob("processor*") if p.is_dir())
    force_dat = sorted(str(f.relative_to(case_root)) for f in case_root.rglob("force.dat"))

    remote_case_root = f"{submission['case_remote_path']}/{CASE_ROOT_DIRNAME}"
    executor = _executor(args, timeout_s=600)
    depth3 = executor.run(
        f"find {remote_case_root} -maxdepth 3 -type d -regex '.*/[0-9.]+' | wc -l"
    )
    depth4 = executor.run(
        f"find {remote_case_root} -maxdepth 4 -type d -regex '.*/[0-9.]+' | wc -l"
    )

    cost = read_fluid_cost_history(case_root / "Fluid.log")
    reports = solver.coupling_report(result)
    fluid_report = next((r for r in reports if r.participant == "Fluid"), reports[0])

    clauses = {
        "L1_mpirun_inside_the_uid_drop": {
            "passed": mpi_element in supervisor and "mpirun" not in before_drop,
            "measured": (
                "the staged supervisor carries the mpirun element exactly once, after the "
                "cd and inside the setpriv drop; nothing before the drop mentions mpirun"
            ),
            "occurrences": supervisor.count(mpi_element),
        },
        "L2_force_dat_in_the_case_root": {
            "passed": force_dat
            == [
                f"{spec.case_subdir}/{spec.fluid_participant_dir}/postProcessing/forces1/0/force.dat"
            ],
            "measured": force_dat,
            "note": (
                "re-measured on the REAL COUPLED deck; session 9's L2 was a fluid-only "
                "screen. The readout globs the case root and needs no change under "
                "decomposition"
            ),
        },
        "L4_processor_count_equals_the_request": {
            "passed": len(processor_dirs) == ranks,
            "requested": ranks,
            "found": len(processor_dirs),
            "dirs": processor_dirs,
        },
        "L6_both_participants_exited_cleanly": {
            "passed": status.stopped_by == "all-exited"
            and all(o.returncode == 0 for o in status.outcomes),
            "stopped_by": status.stopped_by,
            "returncodes": {o.name: o.returncode for o in status.outcomes},
            "n_nonconverged": fluid_report.n_nonconverged,
        },
    }
    record: dict[str, Any] = {
        "adr": "ADR-040",
        "clause": "L6-smoke",
        "kind": "parallel-coupled-smoke",
        "gated": False,
        "started_at": _utc_now(),
        "submission": submission,
        "clauses": clauses,
        "passed": all(c["passed"] for c in clauses.values()),
        "n5_rank_aware_disk_accounting": {
            "time_dirs_maxdepth_3": int(depth3.stdout.strip()) if depth3.returncode == 0 else -1,
            "time_dirs_maxdepth_4": int(depth4.stdout.strip()) if depth4.returncode == 0 else -1,
            "note": (
                "ADR-040 N5 measured: under decomposition OpenFOAM writes time directories "
                "to processor*/<time>, one level deeper than the serial layout. The "
                "maxdepth-3 form the collector used before this session reads essentially "
                "zero on a parallel run, so the F4 disk projection would have seen no "
                "growth at all"
            ),
        },
        "cost": {
            "n_fluid_step_solves": len(cost.steps),
            "windows_completed": fluid_report.n_windows,
            "iterations_per_window_mean": fluid_report.mean_iterations,
            "total_clock_s": cost.total_clock_s,
            "seconds_per_step_solve": cost.total_clock_s / max(1, len(cost.steps)),
            "rank0_cpu_over_wall": cost.total_execution_s / max(1e-9, cost.total_clock_s),
            "admissibility": (
                "MAY NOT SIZE ANYTHING. This is a startup-dominated 20-window smoke: its "
                "iterations per window are the coupling's start-up transient, not the "
                "campaign's, and its wall clock includes the coded function object's first "
                "compilation. Only ADR-040 N3 -- coupled, contended, past the ramp -- may "
                "size B2. rank0_cpu_over_wall is RANK 0's CPU under mpirun (ADR-040 N5) "
                "and is NOT comparable to I10's 99.42 percent aggregate bound"
            ),
        },
    }
    out = Path(args.out or _REPO_ROOT / "data/vv/stage20_l6_smoke.json")
    _write_bundle(record, out)
    for name, clause in sorted(clauses.items()):
        print(f"  {'PASS' if clause['passed'] else 'FAIL'}  {name}")
    return 0 if record["passed"] else 1


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


def _assert_within_probe_ceiling_040(timeout_s: int) -> None:
    """ADR-040 B0. A pre-declared ceiling that the driver does not enforce is a wish."""
    if timeout_s > PROBE_CEILING_040_S:
        raise SystemExit(
            f"--timeout {timeout_s} exceeds ADR-040 B0's per-submission probe ceiling of "
            f"{PROBE_CEILING_040_S} s (72 h). Reaching a ceiling is a recorded outcome "
            "(B4); raising one without a new ADR is not"
        )


def _add_commit(path: Path) -> str | None:
    """The commit that ADDED `path`, or None. `--diff-filter=A`, oldest-last."""
    log = (
        subprocess.run(
            [
                "git",
                "-C",
                str(_REPO_ROOT),
                "log",
                "--diff-filter=A",
                "--format=%H",
                "--",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        .stdout.strip()
        .splitlines()
    )
    return log[-1] if log else None


def _merge_base_guard_040() -> None:
    """ADR-040's P5: its first commit must precede the N3 record's first commit.

    A separate function with a separate record path, not a parameter on ADR-039's. The
    guard resolves commits with ``git log --diff-filter=A``, which returns the commit that
    ADDED a file -- so pointing it at ``stage20_i4_calibration.json`` would compare
    ADR-040 against session 7's add-commit and pass on an ordering that says nothing about
    ADR-040. The N3 record is therefore a NEW file, and this is the guard that makes that
    matter.
    """
    record = _REPO_ROOT / "data/vv/stage20_n3_confirmation.json"
    if not record.exists():
        raise SystemExit(
            "ADR-040 P5/N3: no N3 record exists (data/vv/stage20_n3_confirmation.json) — "
            "the coupled confirmation has not run and nothing may be gated"
        )
    adr = _add_commit(_ADR_040)
    n3 = _add_commit(record)
    if not adr or not n3:
        raise SystemExit(
            "ADR-040 P5: cannot resolve the ADR-040 or N3 record add-commit — refusing a gated run"
        )
    check = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "merge-base", "--is-ancestor", adr, n3], check=False
    )
    if check.returncode != 0:
        raise SystemExit(
            "ADR-040 P5: git merge-base --is-ancestor says ADR-040's first commit does not "
            "precede the N3 record — the pre-registration ordering is broken"
        )


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
    parser.add_argument(
        "--numerics",
        choices=sorted(NUMERICS_STACKS),
        default="adr039-baseline",
        help="the pre-registered linear-solver stack, BY NAME (ADR-040 N1)",
    )
    parser.add_argument(
        "--ranks", type=int, default=1, help="fluid MPI ranks (ADR-040 L3 pre-registers 4)"
    )
    parser.add_argument("--collect-probe", type=Path)
    parser.add_argument("--collect-cost", type=Path)
    parser.add_argument("--record-l6", type=Path, dest="record_l6")
    parser.add_argument(
        "--record-q1", nargs=2, metavar=("FLEX_SUBMISSION", "RIGID_SUBMISSION"), dest="record_q1"
    )
    parser.add_argument("--concurrent-with", nargs="*", default=None)
    parser.add_argument("--submit", choices=sorted(ARMS))
    parser.add_argument("--submit-040", choices=sorted(ARMS), dest="submit_040")
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
        if float(format(max_time, ".13e")) != max_time:
            raise SystemExit(
                f"{args.probe_windows} x {args.probe_dt} = {max_time!r} does not survive "
                "the .13e round trip the CalculiX field width requires (handoff 6.17/6.30) "
                "— 50725 x 2e-5 does not, 50726 does; pick the next window count that does"
            )
        if args.numerics != "adr039-baseline" or args.ranks > 1:
            _assert_within_probe_ceiling_040(args.timeout)
        _prepare_and_submit(
            args,
            arm=arm,
            rung=rung,
            time_window_size=args.probe_dt,
            max_time=max_time,
            gated_intent=False,
            label="probe",
            numerics_label=args.numerics,
            mpi_ranks=args.ranks,
        )
        return 0
    if args.collect_probe:
        return _collect_probe(args)
    if args.collect_cost:
        return _collect_cost(args)
    if args.record_l6:
        return _record_l6(args)
    if args.record_q1:
        return _record_q1(args)
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
    if args.submit_040:
        missing = [
            name
            for name, value in (
                ("GATED_040_TIME_WINDOW_S", GATED_040_TIME_WINDOW_S),
                ("GATED_040_MAX_TIME_S", GATED_040_MAX_TIME_S),
                ("GATED_040_NUMERICS_LABEL", GATED_040_NUMERICS_LABEL),
                ("GATED_040_MPI_RANKS", GATED_040_MPI_RANKS),
            )
            if value is None
        ]
        if missing:
            raise SystemExit(
                "refusing --submit-040: the ADR-040 sentinels are None "
                f"({', '.join(missing)}) — ADR-040 B2 is pending its N3 record; run the "
                "coupled confirmation first"
            )
        _merge_base_guard_040()
        assert is_gated_configuration_040(
            rung=GATED_RUNG,
            time_window_size=GATED_040_TIME_WINDOW_S,
            max_time=GATED_040_MAX_TIME_S,
            numerics_label=GATED_040_NUMERICS_LABEL,
            mpi_ranks=GATED_040_MPI_RANKS,
        )
        _prepare_and_submit(
            args,
            arm=args.submit_040,
            rung=GATED_RUNG,
            time_window_size=GATED_040_TIME_WINDOW_S,
            max_time=GATED_040_MAX_TIME_S,
            gated_intent=True,
            label="wave1",
            numerics_label=GATED_040_NUMERICS_LABEL,
            mpi_ranks=GATED_040_MPI_RANKS,
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
        "choose a mode: --probe / --collect-probe / --collect-cost / --record-l6 / "
        "--record-q1 / --submit / --submit-040 / --status / --collect / --verdict"
    )


if __name__ == "__main__":
    raise SystemExit(main())
