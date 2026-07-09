# ADR-024 — Flapping kinematics primitive + motion-solver tiering (morph → solid-body → overset)

- **Status:** proposed (the design + the SIF-grammar facts are settled; the morph-vs-solid-body
  *tier of record* is confirmed by the Stage-14 R0/R1 cluster probe — the "Validation evidence"
  section is filled at that point, then the ADR is accepted)
- **Date:** 2026-07-09
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 14)
- **Stage:** 14 (Rigid Flapping-Wing Validation)
- **Supersedes:** none (extends ADR-018's moving-mesh motion-solver decision to large-stroke hover)

## Context and problem statement

Stage 14 validates a rigid 2-D flapping wing in hover against Wang, Birch & Dickinson (2004).
The Stage-11 moving-mesh primitive (`aero/adapters/openfoam/motion.py::MotionSpec`) does **pure
heave** only — a single translational `oscillatingDisplacement` hardcoded to +y. A flapping wing
adds **pitch (rotation about a moving spanwise pivot)** combined with the translational stroke,
at an arbitrary **phase offset** between the two (the advanced / symmetrical / delayed rotation
timing — Dickinson 1999). Two decisions are needed: **how to represent the combined kinematics**,
and **which mesh-motion solver** carries an 8×-larger stroke than Stage 11 (A0/c = 2.8 vs the
plunging h0/c = 0.175) plus a ±45° pitch.

ADR-018 anticipated exactly this: it chose morphing (`displacementLaplacian`) as the Stage-11
primary and named overset (`overPimpleDyMFoam`) as the documented fallback, with the escalation
trigger being "a `checkMesh` non-orthogonality/skew blow-up or a solver failure at the target
amplitude … the flapping capstone (Stage 14+, large stroke) may need to escalate." It also
**rejected `solidBodyMotionFvMesh`** — but that rejection was *freestream-specific*: translating
the whole mesh moves the far field / inlet relative to the oncoming stream and contaminates the
`forceCoeffs` reference frame. **In quiescent hover there is no freestream**, so that objection
does not apply, which re-opens solid-body motion as a legitimate — and mesh-quality-exact —
option here.

## Decision drivers

- **Arbitrary phase + ramp are required.** Stock sinusoidal BCs (`oscillatingDisplacement`,
  `angularOscillatingDisplacement`, `oscillatingRotatingMotion`) each impose a *single* fixed
  sinusoid; none composes translation + rotation-about-a-moving-pivot at an independent phase, and
  none admits a startup ramp. The advanced/delayed variants are defined by that phase, so a stock
  BC cannot express them.
- **Impulsive-start stability.** The fine plunging mesh SIGFPE'd at the impulsive heave start
  (Stage 13); a larger stroke is worse. The startup must begin from rest (zero initial linear AND
  angular velocity).
- **Reuse ADR-018 assets.** The morph path reuses `dynamic_mesh_dict` (displacementLaplacian +
  inverseDistance), `transient_fvsolution(cell_displacement=True)`, and the `movingWallVelocity`
  discipline verbatim.
- **Honest force frame in hover.** No freestream ⇒ `forceCoeffs` (divides by `magUInf`) is
  unusable; the dimensional `forces` FO is the only correct measurement (normalised in
  `aero/postprocess/flapping_forces.py`).
- **Serial-only compute** (MPI blocked in the LXC) ⇒ prefer the option that runs stably at the
  target amplitude on the coarsest adequate mesh; a cheap motion-only probe should decide the tier
  *before* any flow solve is spent.

## SIF grammar (verified read-only against the ESI v2412 SIF)

- `solidBodyMotionDisplacement` pointPatch BC — present (`libdynamicMesh`).
- Solid-body motion functions incl. `tabulated6DoFMotion`, `multiMotion`,
  `oscillatingRotatingMotion` — present (`libmeshTools`, auto-loaded).
- Binaries `pimpleFoam`, `overPimpleDyMFoam`, `moveDynamicMesh`, `checkMesh`, `foamToVTK` — all
  present (no SIF rebuild for any tier).
- `tabulated6DoFMotion` table format `(t ((tx ty tz) (rx ry rz)))`, rotation = Euler-XYZ in
  **degrees** (confirmed from the sloshingTank tutorial table, whose rotation peaks ~30 for a tank
  tilt). For a 2-D planar wing only the z-rotation is nonzero, which is convention-independent.

## Considered options

### Kinematics representation
1. **numpy-generated `tabulated6DoFMotion` table** (chosen) — the pivot translation + pitch
   deviation (about the initial pivot = `CofG`) sampled densely (512/cycle), with a C1 `(1-cos)`
   startup ramp baked in. Expresses arbitrary phase + ramp exactly; the table starts at the
   identity transform so the written mesh is the solve's t=0 state.
2. `multiMotion` of stock `oscillatingLinearMotion` + `oscillatingRotatingMotion` — rejected: the
   two stock sinusoids share a phase, so the advanced/delayed offset is inexpressible, and no ramp.

### Mesh-motion solver (the tier of record)
- **A — Morph (PRIMARY):** `dynamicMotionSolverFvMesh` + `displacementLaplacian` +
  `solidBodyMotionDisplacement` on the wing patch. Far field genuinely fixed; reuses every ADR-018
  asset; deformation bounded (±1.4c translation + 45° pitch absorbed across a 25c domain with the
  near-wall layer frozen by `inverseDistance`). Risk: mesh quality at 8× the Stage-11 amplitude
  with rotation.
- **B — Whole-domain solid-body (FALLBACK-1):** `motionSolver solidBody` + the identical tabulated
  function. Kinematically exact, zero deformation, zero `checkMesh` risk, same `pimpleFoam` binary.
  ADR-018's solid-body rejection is freestream-specific and does not apply in quiescent hover;
  residual concern is the far field sweeping ≤1.4c through still fluid (mitigated by the 25c domain
  + a one-off domain-size sensitivity check if B becomes the tier of record).
- **C — Overset (FALLBACK-2):** `overPimpleDyMFoam` + background/component meshes + `liboverset`
  (in the SIF). Robust at any amplitude; largest build (dual-mesh topology, interpolation
  dissipation). Only if A **and** B fail.

## Decision outcome

**Kinematics:** the numpy `tabulated6DoFMotion` table (option 1). **Motion-solver tiering:** morph
PRIMARY → solid-body FALLBACK-1 → overset FALLBACK-2, selected by a **pre-declared probe**:

> **R0 probe (motion-only, minutes):** run `moveDynamicMesh` through ≥1 full stroke cycle (no
> flow) and `checkMesh` at the four kinematic extremes (peak +/− translation, peak +/− rotation).
> **Escalate morph → solid-body** iff any of: `max non-orthogonality > 70`, `max skewness > 4`,
> negative cell volumes, or a mesh-motion solver failure at the target amplitude. **Escalate
> solid-body → overset** iff the solid-body solve is unstable or a domain-size sensitivity check
> shows far-field influence above the numerical-uncertainty floor.

The chosen tier is provenance-visible via the `FlappingWingSpec.mesh_motion` field. Hover forces
are the dimensional `forces` FO with `CofR` at the pivot; coefficients use the WBD normalisation.
The startup uses a C1 `(1-cos)` ramp over `ramp_cycles` (zero initial linear + angular velocity);
the post-ramp limit cycle is ramp-independent.

## Validation evidence (filled from the Stage-14 R0/R1 probe)

- R0 `checkMesh` at the four kinematic extremes: **[pending cluster R0]**.
- Tier of record (morph vs solid-body vs overset): **[pending]**.
- R1 symmetry regression (mean C_D ≈ 0, mean C_L > 0 over a symmetric-rotation cycle) and, if run,
  the morph-vs-solid-body trace cross-check: **[pending]**.

## Consequences

- **Positive:** one motion primitive expresses the whole flapping family (incl. the Stage-15
  optimizer's `pitch_phase_deg` design variable); the tier decision is made cheaply before flow
  solves; ADR-018's assets are reused; the hover force frame is honest.
- **Negative / risk:** morph mesh quality at large stroke is unproven until R0 (mitigated by the
  cheap probe + the ~20-line switch to solid-body, provenance-visible); the `tabulated6DoFMotion`
  rotation convention is settled from the SIF but is also visually re-confirmed by the R0 frame
  dump (belt-and-braces).
- **Ledgered:** a domain-size sensitivity study is required *iff* solid-body becomes the tier of
  record (the far field then moves through the quiescent fluid).

## Links

- Extends: ADR-018 (moving-mesh motion solver — morph primary, overset fallback; solid-body
  rejected *for freestream flows*), ADR-019 (unsteady postprocess API), ADR-022 (Stage-13 unsteady
  resolution).
- Stage prompt: `docs/handoff-bundle/STAGE-14-rigid-flapping-wing.md`; pre-registration:
  `docs/vv/stage14-preregistration.md`; rule: `.claude/rules/flapping-validation-ladder.md`.
- External: Wang, Birch & Dickinson (2004) *J Exp Biol* 207:449–460; Dickinson, Lehmann & Sane
  (1999) *Science* 284:1954.
