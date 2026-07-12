# ADR-024 — Flapping kinematics primitive + motion-solver tiering (morph → solid-body → overset)

- **Status:** accepted (the R0 cluster probe decided the tier of record: morph eliminated on mesh
  failure, solid-body rejected on physics, **overset chosen** and validated end-to-end — see
  "Validation evidence")
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

### Mesh-motion solver (the tier of record — decided by the R0 probe, evidence below)
- **A — Morph:** `dynamicMotionSolverFvMesh` + `displacementLaplacian` +
  `solidBodyMotionDisplacement` on the wing patch. Far field fixed; reuses every ADR-018 asset.
  **Tested (R0): FAILS at full stroke** — the ±1.4c translation of a thin body tears the
  deforming O-grid (skewness 5503, 18145 inverted face-pyramids / negative volumes). Retained in
  the code (`mesh_motion="morph"`) only as a documented small-amplitude alternative.
- **B — Whole-domain solid-body:** `motionSolver solidBody` + the identical tabulated function.
  **Rejected — physically inappropriate.** It moves the ENTIRE mesh (wing + far field) rigidly,
  which is an accelerating reference frame *without* the fictitious (inertial) body forces
  (OpenFOAM's `solidBody` adds none): there is no wing-relative-to-quiescent-fluid motion at the
  boundary, so no aerodynamics develops. Fine for a gravity-driven sloshing tank; wrong for a body
  oscillating in still fluid. (This corrects an earlier draft of this ADR that mistakenly claimed
  hover reversed ADR-018's solid-body rejection — the deeper non-inertial-frame objection applies
  in hover too. Corroboration: the ESI moving-wing tutorials use AMI/overset, never whole-mesh
  solid-body; R0 confirmed the mesh stays perfect precisely *because nothing moves relative to the
  fluid*.)
- **C — Overset (CHOSEN, tier of record):** `overPimpleDyMFoam` + `dynamicOversetFvMesh`. The wing
  sits on a small **component** O-grid (outer boundary type `overset`) that moves **rigidly** via
  `multiSolidBodyMotionSolver` + `tabulated6DoFMotion` over a **fixed** Cartesian background mesh
  (open `farfield`). Far field genuinely fixed, nothing deforms, any amplitude admissible — the
  standard approach for large-amplitude flapping, and what the SIF's own moving-body overset
  tutorials use. Cost: a dual-mesh build (background + component, `mergeMeshes`, `topoSet`
  cellZones, `setFields` `zoneID`, overset interpolation) — implemented in
  `aero/adapters/openfoam/flapping_wing.py` (the `mesh()` step runs the assembly sequence).

## Decision outcome

**Kinematics:** the numpy `tabulated6DoFMotion` table (option 1). **Motion solver: OVERSET
(option C)** — chosen after the R0 probe eliminated morph (mesh failure) and solid-body (wrong
physics). The tier is provenance-visible via `FlappingWingSpec.mesh_motion` (default `overset`;
`morph` retained for small-amplitude cases). Hover forces are the dimensional `forces` FO with
`CofR` at the pivot; coefficients use the WBD normalisation. The startup uses a C1 `(1-cos)` ramp
over `ramp_cycles` (zero initial linear + angular velocity); the post-ramp limit cycle is
ramp-independent. The `tabulated6DoFMotion` table is generated one period past `endTime` so the
final solver step never queries beyond it.

> **R0 probe (motion-only, cheap; the pre-declared escalation gate):** `moveDynamicMesh` +
> `checkMesh` through a full ramped stroke. Escalate morph → overset iff `checkMesh` shows
> `non-orthogonality > 70` / `skewness > 4` / negative volumes at the target amplitude. (Solid-body
> is not a tier here — it is rejected on physics, not mesh quality.)

## Validation evidence (Stage-14 R0 probe + overset prototype, 2026-07-09)

- **R0 morph:** initial mesh OK (non-ortho 67, skew 1.78); at full stroke **skewness 5503, 18145
  inverted face-pyramids** → morph eliminated (the ADR-018 escalation trigger, fired).
- **R0 solid-body:** mesh quality constant/perfect — but only because the whole mesh moves
  rigidly (no relative motion); rejected on physics, not mesh quality.
- **Overset:** the assembled overset case (`overPimpleDyMFoam`, `dynamicOversetFvMesh`,
  `multiSolidBodyMotionSolver`) **runs stably to completion** at Re = 75 (2.5-cycle prototype +
  the adapter-generated case: `checkMesh` OK non-ortho 67 / skew 1.77; solve rc 0; dimensional
  `forces` produced). Overset is the tier of record.
- R1 symmetry regression (mean C_D ≈ 0, mean C_L > 0 over a symmetric-rotation cycle): **[from the
  Stage-14 campaign, recorded in the handoff]**.

## Consequences

- **Positive:** one motion primitive expresses the whole flapping family (incl. the Stage-15
  optimizer's `pitch_phase_deg` design variable); the far field is genuinely fixed and nothing
  deforms at any amplitude; the hover force frame is honest (dimensional `forces`, WBD normalised).
- **Negative / cost:** overset is a dual-mesh build (background + component, hole-cutting via
  `zoneID`, interpolation dissipation) — larger than the plan's assumed morph/solid-body switch;
  the `mesh()` step is now motion-tier-aware (a compound assembly command for overset).
- **Ledgered:** overset introduces interpolation dissipation and a background-vs-component
  resolution match; the background cell size and component radius are tunable knobs
  (`background_cells`, `component_radius_chords`) — a GCI/resolution sensitivity check on the
  overlap is a follow-up if the anchor is marginal.

## Links

- Extends: ADR-018 (moving-mesh motion solver — morph primary, overset fallback; solid-body
  rejected *for freestream flows*), ADR-019 (unsteady postprocess API), ADR-022 (Stage-13 unsteady
  resolution).
- Stage prompt: `docs/handoff-bundle/STAGE-14-rigid-flapping-wing.md`; pre-registration:
  `docs/vv/stage14-preregistration.md`; rule: `.claude/rules/flapping-validation-ladder.md`.
- External: Wang, Birch & Dickinson (2004) *J Exp Biol* 207:449–460; Dickinson, Lehmann & Sane
  (1999) *Science* 284:1954.
