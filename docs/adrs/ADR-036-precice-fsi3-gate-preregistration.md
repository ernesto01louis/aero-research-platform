# ADR-036 — Pre-registered FSI3 gates: pins P, config C, pre-flight I, reference R, coupling K, steady-state S, displacement D

- **Status:** accepted
- **Date:** 2026-07-27
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 19)
- **Stage:** 19
- **Supersedes:** —

## Context and problem statement

Stage 19 verifies partitioned fluid-structure coupling on the supported upstream
Turek-Hron FSI3 tutorial. The verification is worth something only if every gate — which
versions, which configuration, which reference row, what counts as converged, which part
of the record is analysed, and how close is close enough — is fixed **before** the
campaign runs. Stages 15-18 retracted, blocked or capped five would-be shortcuts; the
gates are the product.

FSI3 makes this sharper than Stage 18 did, for three reasons. The run is long (hours to
days, serial), so there is real pressure to stop early and take what is there. The
quantity is an oscillation amplitude, so *which* window you measure changes the answer.
And an implicit coupling that exhausts `max-iterations` does not crash — preCICE carries
on and keeps producing numbers.

This ADR is the pre-registration of record. **The gate block below is duplicated verbatim
as `PREREGISTERED_GATE_BLOCK` in `scripts/stage19_turek_hron_fsi3.py` — the operational
copy, which is embedded in every campaign bundle — and a required-CI unit test asserts the
two are byte-identical.** Stage 18 kept a hand-maintained paraphrase and had to rely on
discipline; putting the block in the artifact and checking it in CI does not.

## Decision drivers

- **A pre-registration that cannot fail is worthless** (the ADR-032 lesson: a degenerate
  protocol produces an honest but uninformative result). Bands must be sized against the
  reference's own uncertainty, not against what we expect to achieve.
- **The analysis window is where an amplitude gate leaks.** If a human picks it, the gate
  is advisory.
- **Silent failure modes dominate.** Non-converged coupling, a mis-identified reference
  row, a transposed watch-point column, a partially-written file: each yields a plausible
  number.
- **A budget NO-GO must be available and honest** (ADR-016's staged claims), otherwise
  budget pressure turns into band pressure.

## Considered options

1. **Gate the transverse amplitude and frequency only.** Narrowest claim; leaves the
   streamwise response unverified, which is what Stage 20's flexible wing inherits.
2. **Gate all six published quantities** (both displacement components' mean, amplitude
   and frequency).
3. **Two-tier: gate five quantities, with the ill-conditioned transverse mean and the
   force quantities as diagnostics** — the option taken.

## Decision outcome

Chose **Option 3**. Option 2 fails on the transverse mean: it is ~3 % of its own
amplitude, and re-segmenting the *published reference itself* at a period 1.5 % different
moves it by ~50 % (9.66e-4 → 1.4656e-3), while the streamwise mean moves 0.9 %. A relative
tolerance on it would measure our segmentation, not the coupling — the same reasoning
that made CFD3's near-zero mean lift a diagnostic in ADR-034, but here quantified rather
than argued by analogy. Option 1 is defensible but leaves the second-harmonic streamwise
response — the part of the motion most sensitive to the solid model — entirely unchecked.

<!-- GATE-BLOCK:BEGIN -->
```text
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
```
<!-- GATE-BLOCK:END -->

### Why the bands can actually fail

A pre-registration is degenerate when no plausible outcome falls outside it. For D1:

- the reference's **own** spread across mesh levels is **2.1 %** on the transverse
  amplitude (L2 3.573e-2 → L4 3.499e-2) and under 0.5 % across its three time steps. A
  15 % band is about 7× the reference's own uncertainty — not 50×;
- the failure modes are live. Upstream ships `_refined` and `_double_refined` precisely
  because the ~21k default mesh is not converged; the FSI3 limit-cycle amplitude is a
  self-excited, added-mass-dominated quantity whose partitioned-solver spread in the
  literature is routinely 5-15 %; and the RBF mapping's support radius is fixed at 0.35
  while the fluid spacing changes with the rung. A miss beyond 15 % is a real possibility;
- D2 at 5 % is bounded from below by our own estimator: recomputing the reference with it
  lands **+1.46 %** off the tabulated frequency, on an 8-cycle record with a 0.693 Hz FFT
  bin. Adding ~2 % of published level-to-level spread leaves little room, so 5 % is about
  as tight as the estimator honestly allows — and it is deliberately **not** tight enough
  to discriminate level 2 from level 4 (1.8 %). That is a limitation, stated rather than
  hidden;
- D3/D4 at 25 % are derived rather than tuned: flag-tip chordwise shortening scales as the
  square of the transverse deflection, so a first-order band on the streamwise response is
  about twice the transverse band;
- the gated set is not padded with easy wins. Everything that reproduces to ≤1 % on the
  reference — the force quantities — is a diagnostic. Passing D requires the flag's motion
  itself to be right.

A note against ourselves: 15 % on D1 was chosen by the operator before the 2.1 % figure
above was measured. On the evidence, 10 % would also have been defensible (≈5× the
reference's own spread) and would have made the gate harder. The band is recorded as
chosen, un-narrowed and un-widened, because moving it *after* seeing the evidence is
exactly the move this document exists to prevent.

### Consequences

**Positive.** The window, the period, the reference row and the convergence criterion are
all decided by rule and enforced in code paths that a V&V run cannot bypass — `load()`
raises before any number is returned. The budget ceiling is a recorded outcome, so a NO-GO
on budget is available without touching a band. The reference is recomputed by the same
function that measures the solve, so a definitional mismatch cannot hide in the comparison.

**Negative (honest limits).** The bands are engineering judgement anchored to the
reference's own discretisation spread, not to a platform-owned convergence study; no GCI
is claimed and the tier target is `validated`, not thesis-grade. D5 is correlated with D2
and is labelled as such rather than counted as independent evidence. One mesh rung bears
the gate. And the whole claim is about *coupling correctness* on a benchmark with a
Nutils solid — application fidelity for a flexible wing with a CalculiX solid is a
separate claim with its own reference (ADR-016), which Stage 20 must make on its own.

**Neutral / followup.** If the campaign reaches the ceiling before S3 is satisfied, the
honest result is a budget NO-GO with the machinery shipped; the infrastructure gap
(serial-only, MPI blocked) is then the finding, and it should be recorded as such rather
than treated as a failure of the physics.

## Pros and cons of considered options

**Option 1 — transverse only**
- Good: gates only the best-conditioned quantities; least likely to produce a NO-GO.
- Bad: the streamwise response, most sensitive to the solid model, goes unverified —
  and that is precisely what Stage 20 builds on.

**Option 2 — gate all six**
- Good: superficially the most complete.
- Bad: includes the transverse mean, whose value is set by the segmentation period rather
  than by the physics; a band on it is either meaningless or has to be inflated, and
  inflating it is the failure mode this whole discipline exists to prevent.

**Option 3 — two-tier, five gated (chosen)**
- Good: everything gated is well conditioned; everything ill-conditioned is reported.
- Good: the correlated frequency check is kept but labelled, rather than dropped or
  double-counted.
- Bad: five bands is more surface to defend than two.

## Links

- ADR-035 (pins, container strategy, adapter shape), ADR-016 (the FSI strategy this
  verifies), ADR-034 and ADR-032 (the pre-registration pattern mirrored here), ADR-019
  (the post-processing toolkit `limit_cycle` extends).
- `data/references/fsi/turek_hron_fsi3/reference.md` — reference identification evidence,
  the R2 agreement table, and the two measured extraction traps.
- `scripts/stage19_turek_hron_fsi3.py` — the operational copy of the block above.
- `.claude/rules/flapping-validation-ladder.md` — the FSI tier this satisfies.
