# ADR-021 — Transition model: `kOmegaSSTLM` (gamma-Re_theta) pin + T3A onset verification

- **Status:** accepted
- **Date:** 2026-07-06
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 13)
- **Stage:** 13
- **Supersedes:** none (extends ADR-017's forward-regime V&V, ADR-005 TMR harness)

## Context and problem statement

The flapping-wing flagship operates at Re ~ 10^2-10^4 — a **transitional** regime where
fully-laminar and fully-turbulent RANS both mispredict the boundary-layer state. Stage 12
exposed this concretely: a 2-D laminar plunging NACA-0012 over-predicts thrust ~2-4x vs the
(primary-source-verified) Heathcote-Gursul experiment. Stage 13 must add a transition-capable
turbulence path to the OpenFOAM adapter and **pin + verify** it before the Stage-14 rigid-
flapping flagship is built on top of it (Hard Rule 8 — PIN HEAVY DEPS; Hard Rule 15 —
VALIDATE-AGAINST-EXPERIMENT).

## Decision drivers

- OpenFOAM-ESI **v2412 is already pinned** (ADR-003); its native transition model is the
  Langtry-Menter gamma-Re_theta four-equation model `kOmegaSSTLM`.
- A transition model is worthless unpinned + unverified — the predicted onset location is
  sensitive to the free-stream-turbulence decay from inlet to the leading edge.
- PLATFORM-NOT-HUB / FAIL-LOUD / provenance still hold; the addition must not perturb the
  existing laminar / kOmegaSST paths.
- A tolerance is a contract (never relaxed); "within band" must be a pre-declared, defensible
  number.

## Considered options

1. **Pin `kOmegaSSTLM` (ESI v2412 native) + verify onset on a ported ERCOFTAC T3A tutorial.**
2. **Pin `kOmegaSSTLM` but verify on a bespoke parametric transitional flat plate** (reuse the
   TMR flat-plate mesh at elevated FSTI).
3. **A different transition model** (e.g. the one-equation gamma model, or an algebraic
   e^N / BC transition approach).

## Decision outcome

Chose **Option 1**: pin `kOmegaSSTLM` and verify against a **faithful port of the ESI v2412
`incompressible/simpleFoam/T3A` tutorial** (ERCOFTAC T3A, 3% FSTI).

**Adapter binding (the pin).** `turbulence_properties(model)` already renders `RASModel <model>`
generically, so `kOmegaSSTLM` is selected by the string alone. The model transports two extra
fields — **`gammaInt`** (intermittency) and **`ReThetat`** (transition-onset momentum-thickness
Reynolds number), both dimensionless. Stage 13 adds:

- field writers for `gammaInt`/`ReThetat` in `case_writer._fields()` (freestream `inletOutlet`,
  wall `zeroGradient`) + the moving-case `plunging_airfoil._fields()`;
- their transport `div` schemes (`divSchemes` uses `default none`, so they MUST be listed) and
  solver groups in the steady + transient fv dictionaries, gated so the laminar/kOmegaSST output
  is byte-identical;
- the Langtry-Menter freestream `ReThetat(Tu)` correlation (`rethetat_freestream`) used to set the
  inlet `ReThetat` from the free-stream turbulence intensity;
- `"kOmegaSSTLM"` on the `CaseSpec` / `PlungingAirfoilSpec` turbulence-model Literals.

**T3A verification case + metric.** The case (`aero/vv/ercoftac/`) is a **verbatim port** of the
tutorial's 11-block curved-nose flat-plate mesh + fields + solver dicts, kept **dimensional**
(U_inf = 5.4 m/s, nu = 1.5e-5) because the fixed 3% FSTI (Tu = sqrt(2k/3)/U) only holds at the
tutorial's specific U and k — so `wall_distribution` gains an optional `u_inf` for the Cf
non-dimensionalisation. Metrics, declared **a priori**:

- **`transition_onset_rex`** (primary GO metric): Re_x at the Cf **minimum** (a scale-invariant,
  reproducible onset proxy). Reference Cf-min at x = 0.395 m -> Re_x ~= 1.42e5. **Tolerance 0.20**
  (relative) — the accepted gamma-Re_theta onset-prediction band (Langtry & Menter 2009).
- **`cf`** (secondary, pointwise `normalized`): the full Cf(x) curve. **Tolerance 0.25**.

**Result (verified on the cluster, MLflow `b6c4783e`, run
`t3a_flat_plate_transition-20260706-073029`, SHA `0e0a0a7`):** status **PASS** —
`transition_onset_rex` error **18.39%** (< 20%), `cf` error **24.37%** (< 25%). The full Cf(x)
reproduces the laminar dip -> transition rise -> turbulent decay; the model transitions at
Re_x ~= 1.16e5, i.e. **~18% early** vs the experiment (1.42e5) — a real, small model-form tendency
of the ported gamma-Re_theta setup, **within the a-priori band, not tuned to pass**.

### Consequences

- **Positive:** the platform now has a **verified** transitional-RANS path in the flapping
  regime; the transition-onset half of the Stage-13 GO gate is GREEN; the pin (ESI v2412 native
  `kOmegaSSTLM` + `gammaInt`/`ReThetat`) is documented and reproducible.
- **Negative:** the T3A pass margins are tight (18.4%/20%, 24.4%/25%); the onset metric is limited
  by the reference's 100 mm station spacing (the true Cf-min is quantized), which inflates the
  apparent onset error — the Cf(x) curve match is the more substantive validation.
- **Neutral / followup:** the moving-airfoil `kOmegaSSTLM` path (the plunging transition probe) is
  a separate ADR (ADR-022); a full 3-grid GCI on T3A is deferred (steady onset within band suffices
  for the gate).

## Pros and cons of considered options

### Option 1 — pin + verify on the ported T3A tutorial (chosen)
- Good: reproduces a validated tutorial verbatim -> lowest risk that the onset is a setup artifact;
  the ERCOFTAC reference data ships in the SIF (GPL); passes a-priori bands.
- Bad: a dimensional case (breaks the platform's U_inf=1 convention -> needs the `u_inf` seam); the
  ported mesh is fixed (refinement only via a cell-count multiplier).

### Option 2 — bespoke parametric transitional flat plate
- Good: fits the platform's parametric-case pattern; U_inf=1.
- Bad: the transition location depends on the inlet-to-LE turbulence decay, which a generic flat-
  plate mesh would not reproduce without careful tuning -> high risk of a mislocated onset that is
  a mesh artifact, not a model result. Rejected as higher-risk for a GO-critical case.

### Option 3 — a different transition model
- Good: some algebraic models are cheaper.
- Bad: `kOmegaSSTLM` is the ESI-native, tutorial-validated choice already in the pinned SIF; a
  different model is unpinned scope creep with no payoff for the mission. Rejected (SCOPE-GATE).

## Links

- Stage prompt: `docs/handoff-bundle/STAGE-13-transition-and-unsteady-airfoil.md`
- Related ADR: ADR-017 (forward-regime + transient seed), ADR-005 (TMR harness), ADR-022 (plunging
  re-anchor + transition probe), ADR-003 (OpenFOAM-ESI v2412 pin)
- Related handoff: `docs/handoffs/STAGE-13-transition-and-unsteady-airfoil-DONE-2026-07-06.md`
- External: Langtry & Menter (2009), AIAA J 47(12):2894; Menter et al. (2006); Savill (1993, 1996);
  ERCOFTAC T3A; OpenFOAM-ESI v2412 tutorial `incompressible/simpleFoam/T3A`.
