# ADR-039 — Pre-registered Heathcote-Gursul gates: pins P, config C, pre-flight I, reference R, coupling K, steady-state S, alignment A, fidelity D, mesh M

- **Status:** accepted
- **Date:** 2026-08-10
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 20)
- **Stage:** 20
- **Supersedes:** — (ADR-036 remains the Stage-19 pre-registration; its P3 clause is
  retired by ADR-038 and rewritten here, not amended there)

## Context and problem statement

Stage 20 validates a chordwise-flexible plunging foil — OpenFOAM fluid and CalculiX solid
in **two** containers, coupled by preCICE — against the Heathcote & Gursul (2007)
*experiment*. The claim is **application fidelity** (ADR-016), distinct from Stage 19's
coupling correctness, and its headline is an **increment**: the flexible foil out-thrusts
the essentially-rigid control at the same operating point. The verification is worth
something only if every gate is fixed **before** the campaign runs.

Stage 20 is sharper than Stage 19 in four ways. The campaign is two waves of multi-day
runs, so budget pressure is real. The gated quantity set spans two *arms* whose specs
differ in exactly one number, so a silent cross-arm mismatch produces a plausible chimera
rather than an error. Several clauses (the increment D3/D4, the sign predicates D5/D6,
the admissibility predicate D7, the reported-only D9) are structurally invisible to the
V&V dashboard — `BenchmarkRunner.run` folds status over `metrics()` alone — so they exist
only if the campaign driver evaluates them. And the reference is an experiment whose own
figures and prose disagree in one documented place, so the reference of record had to be
recomputed and pinned first (R-family).

This ADR is the pre-registration of record. **The gate block below is duplicated verbatim
as `PREREGISTERED_GATE_BLOCK` in `scripts/stage20_hg2007_flexible_foil.py` — the
operational copy, embedded in every campaign bundle — and required-CI unit tests assert
the two are byte-identical and that the block's ordered `(clause, band)` list equals
`aero/vv/fsi/hg2007_flexible_foil.py:CLAUSE_BANDS`.** ADR-036's parity test silently
dropped its band-less clauses (its regex could not see `D9`/`D10` at all — four measured
defects, handoff §6.13/§8); here `(no band)` is a first-class token and the parity is
ordered and exhaustive.

## Decision drivers

- **A pre-registration that cannot fail is worthless** (ADR-032). The bands are sized by
  a pre-registered rule against the reference's own uncertainty — and where the rule's
  floor binds, the ADR says the number is policy, not derivation.
- **Silent-wrong-number failure modes dominate this stage.** Sessions 4-6 measured ten of
  them (different coupling iterates kept by the two readers; an under-loaded 400x slab;
  `INC` exhaustion with rc=0; a forged manifest; an unverified time base; …). Each yields
  a plausible number, not a crash. The C/A families exist to state the closures that are
  now enforced in code.
- **The analysis window is where an amplitude gate leaks** — it is derived by rule (S),
  never chosen.
- **A budget NO-GO must be available and honest** (ADR-016), otherwise budget pressure
  becomes band pressure. Two waves, per-wave ceilings, and declared last resorts.
- **The increment is the mission** (Hard Rules 12/14; `.claude/rules/optimization-
  integrity.md`): matched numerics across arms, paired-difference statistics, and a
  clause-by-clause verdict so "NO-GO on absolute fidelity, GO on the flexibility
  increment" is expressible in the bundle.

## Considered options

1. **Gate the absolute quantities only** (C_T, eta, pitch amplitude on the flexible arm).
   Simplest, but the headline claim — the flexibility *increment* — would ride ungated,
   and ADR-022 measured this platform's 2-D plunging solve missing HG's absolute rigid
   thrust by -28 %/+58 %, so an absolute-only gate is the one most likely to fail for a
   reason (2-D vs 3-D model form) the increment partially cancels.
2. **Gate the increment only.** Honest about ADR-022's model-form risk, but a verdict
   blind to a 60 % absolute miss would dress a differencing trick up as fidelity.
3. **Gate both, resolved clause by clause** — the option taken, operator-chosen (handoff
   §2), knowing a NO-GO on the absolute clauses is a live outcome.

## Decision outcome

Chose **Option 3**. The verdict is resolved clause by clause in the bundle, both the
absolute bands and the increment sit in the VERDICT line, D9 is reported-only (its
companion D8 admits enough rigid-arm pitch to bias the naive formula 12 %, so D8 and D9
could not both be satisfiable — session-4 operator decision), and D10 stays gated as a
genuine closure identity.

<!-- GATE-BLOCK:BEGIN -->
```text
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
     >= 10*ceil(max_time/dt), never copied; n_through_thickness even (odd has no
     mid-surface node and preCICE snaps the watch-point silently).
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
```
<!-- GATE-BLOCK:END -->

### Why the bands can actually fail

- **D1/D3 are live in the literature and in this repo's own record.** ADR-022 measured
  the platform's 2-D plunging solve against the *other* HG experiment at -28 %/+58 % on
  absolute thrust with an St-dependent slope error. Stage 20 removes one of its two root
  causes (the geometry substitution) but not the other (2-D vs 3-D at aspect ratio 3.3
  with end plates). A miss beyond 25 % on D1 is a genuinely expected outcome class, and
  if the error is multiplicative the increment inherits it into D3.
- **D2's band is the one the 4x rule actually set** (0.401 → 0.40): efficiency divides
  two gauge readings and carries the thesis's own stated 10 % instrument term.
- **D0 has never been measured on this platform.** The pitch amplitude *is* the
  flexibility physics; nothing upstream of this stage constrains it. Getting it inside
  25 % requires the structural model (plane-strain modulus, root clamp at x = 30 mm,
  NLGEOM) to be right, not just the fluid.
- **D10 is a closure identity, not a physics band** — it fails on bookkeeping errors
  (sign conventions, the wrong coupling iterate, ALPHA drift), which sessions 5-6 showed
  are this stage's dominant defect class.
- **The gated set is not padded.** Everything derived or ill-conditioned (C_P, the
  crossover, the naive-power bias) is reported, never gated.

A note against ourselves, mirroring ADR-036's: the 0.25 floor was operator-chosen before
the raw multipliers were computed, and on four of five clauses it binds — for D3/D4 the
4x rule is **decorative** and 0.25 is a policy number. The bands are recorded as chosen,
un-narrowed and un-widened; on the evidence, tighter bands (D3's raw rule gives 2.1 %)
would have been defensible and much harder, and choosing them *after* seeing solver
output is exactly the move this document exists to prevent.

### Two contradictions in the work-of-record, resolved here

1. **Fine-rung dt.** Handoff §6.11 sketched the finest rung at a dt scaled by the
   refinement ratio; the session-4 I8 decision argues a FIXED coupling window across
   rungs makes temporal error common-mode so it cancels from the spatial GCI. These are
   incompatible. **Resolved: dt is fixed across all three rungs.** The cost is that the
   Courant bound must hold on the fine rung's smaller cells (about 1.30x the mid rung's
   Co), which is why I7 probes the fine rung too rather than assuming linear scaling.
2. **Contention.** Wave 1 runs both arms concurrently on one 16-core box; an
   uncontended seconds-per-window would understate the wave. **Resolved: the mid-rung I7
   probes are submitted concurrently — the wave-1 shape — and B2's projection uses that
   contention-measured rate.** The remaining I4 calibrations run concurrently in the
   wave-2 shape for the same reason.

### Consequences

**Positive.** The window, the period, the reference row, the convergence criterion, the
cross-arm comparability and the campaign sizing are all decided by rule and enforced in
code paths a V&V run cannot bypass — `load()` raises before any number exists,
`align_arms` raises rather than degrades, and `is_gated_configuration` returns False
until the pre-flight record exists. The increment's invisibility to the dashboard is
stated in the block itself, so a green dashboard cannot be read as a verdict.

**Negative (honest limits).** The bands are floored policy numbers on four of five gated
scalars, anchored to the reference's uncertainty rather than to a platform-owned
convergence study until wave 2 lands the GCI. The rig is modelled quasi-2-D (2.5 mm
slab) where the experiment had aspect ratio 3.3 with end plates — the ADR-022 model-form
gap is knowingly carried, and a NO-GO on the absolute clauses with a GO on the increment
is the honestly expected shape of the result. D5/D6/D7 and the increment have no
dashboard row; the bundle is the only place they exist.

**Neutral / followup.** If wave 2 never runs, the increment ships with
`u95_delta_numerical` unavailable and the claim caps below thesis-grade — recorded, not
hidden. The B2 marker's three-commit dance (rule now, record next, numbers last) is
enforced by `test_adr039_b2_marker_state.py`.

## Links

- ADR-036 (the Stage-19 pre-registration this mirrors and improves on), ADR-037
  (authored-case integrity contract), ADR-038 (the roster P3 relies on), ADR-016 (why
  coupling correctness and application fidelity never blur), ADR-022 (the measured
  model-form risk), ADR-023/025 (paired-difference and honest-absence precedents).
- `data/references/fsi/heathcote_gursul_2007/reference.md` — reference identification,
  the R2 table, the two live traps (the C_T/St^2 axis; the three-experiment conflation).
- `aero/vv/fsi/hg2007_flexible_foil.py` — `CLAUSE_BANDS`, the sentinels, the derived
  gate; `aero/vv/fsi/hg2007_sizing.py` — the committed pure sizing rule.
- `scripts/stage20_hg2007_flexible_foil.py` — the operational copy of the block.
- `tests/unit/test_adr039_*.py` — byte-identity, shape, parity, marker-state and
  derivation tests (in `tests/unit/` because `tests/stage_20` is not in CI).
