# ADR-018 — Moving-mesh motion solver: morphing primary, overset fallback

- **Status:** accepted
- **Date:** 2026-07-01
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 11)
- **Stage:** 11
- **Supersedes:** none (extends ADR-017's transient seed)

## Context and problem statement

The flapping mission is unsteady **and moving**: prescribed-kinematics plunging/pitching
(Re ~ 10²–10⁴). Stage 10 (ADR-017) proved a transient `pimpleFoam` path on a *static*
cylinder. Stage 11 must make the body move — the prerequisite for any flapping case
(`00-MISSION-AND-SCOPE.md` §3.1). OpenFOAM-ESI v2412 (already pinned) ships several
dynamic-mesh strategies; the stage prompt names `dynamicMotionSolverFvMesh` (rigid-body
oscillation) with AMI / `overPimpleDyMFoam` (overset) "where prescribed motion needs it."
The two Stage-11 validation cases are small-amplitude: the oscillating cylinder A/D ≈ 0.2–0.5
and the plunging airfoil h0/c ≈ 0.175.

## Decision drivers

- **Accuracy in the near-wall region + wake.** The low-Re cylinder drag split and the foil
  leading-edge vortex both need the boundary-layer / wall-normal spacing preserved and a wake
  free of spurious interpolation dissipation.
- **Amplitude vs mesh quality.** Both target amplitudes are small relative to the domain.
- **Code reuse + cost.** Reuse the Stage-10 O-grid / the C-grid and the `pimpleFoam` binary.
- **SCOPE-GATE:** invest effort where the mission needs it; don't build machinery a later
  stage will need before it does.
- Operator directive: the motion-solver choice is the agent's call, with intensive work
  pre-approved ("build something intensive if it's better").

## Considered options

1. **Morphing** — `dynamicMotionSolverFvMesh` + `displacementLaplacian`, an
   `oscillatingDisplacement` `pointDisplacement` BC on the moving wall, fixed far field, and
   an **`inverseDistance` diffusivity** that freezes the near-wall cells (boundary-layer
   preserving). Solver binary unchanged (`pimpleFoam` runs a `dynamicMeshDict` natively).
2. **`solidBodyMotionFvMesh`** — the whole mesh translates rigidly with the body.
3. **Overset** — `overPimpleDyMFoam` + AMI: a body-fitted grid moves rigidly over a static
   background grid.

## Decision outcome

Chose **Option 1 (morphing) as PRIMARY**, with **overset (Option 3) as a documented,
tested-available FALLBACK**. Rationale in one sentence: at these small amplitudes morphing is
not merely cheaper, it is *more accurate* than overset (no overlap-interpolation dissipation
in the wake, the wall-normal layer frozen by the inverse-distance diffusivity), and it reuses
the existing meshes + the `pimpleFoam` binary — so "more intensive" (overset) would be worse,
not better.

**Rejected `solidBodyMotionFvMesh`** (recorded so a future reader does not "simplify" to it):
translating the *entire* mesh moves the far field/inlet relative to the freestream, which for
an **external** flow contaminates the `forceCoeffs` reference frame and the thrust bookkeeping
(you would have to superpose the motion onto the inflow BC, i.e. a non-inertial frame). It is
right for internal/piston flows, wrong for a body oscillating in a fixed freestream.

**New OpenFOAM artifacts per moving case** (grammar verified against the SIF tutorials + BC
source): `constant/dynamicMeshDict` (`dynamicMotionSolverFvMesh` + `displacementLaplacian` +
`diffusivity inverseDistance (<movingPatch>)`); `0/pointDisplacement` (`oscillatingDisplacement`
on the moving wall = `amplitude·sin(ωt)`, far field `fixedValue`, front/back `empty`); the
moving wall's `0/U` BC switched `noSlip → movingWallVelocity` (no-slip in the moving frame —
**getting this wrong silently biases the forces**); and `fvSolution` gains a `"pcorr.*"`
flux-correction solver (`correctPhi`) + a `cellDisplacement` motion solver (`pimpleFoam`
aborts without them). Writers: `aero/adapters/openfoam/motion.py` +
`_foam_common.transient_fvsolution(cell_displacement=True)`.

**`run()` dispatch is unchanged** for the morphing path — ESI merged the moving-mesh solver
into `pimpleFoam` (a case with a `dynamicMeshDict` triggers the dynamic-mesh path), so the
Stage-10 `getattr(spec, "transient")` dispatch already selects the right binary. Only the
overset fallback would add an `overPimpleDyMFoam` branch (keyed on a future motion field, not
on `transient`).

### Validation evidence (this stage)

- **SIF capability probe (aero-build):** `pimpleFoam`, `overPimpleDyMFoam`, `moveDynamicMesh`
  and `libfvMotionSolvers` / `libdynamicMesh` / `liboverset` are all present — the overset
  fallback needs **no SIF rebuild**.
- **Morphing quality at A/D = 0.5 (the harder cylinder amplitude):** `blockMesh` (25 600
  cells) + `pimpleFoam` ran **2 911 steps through the full oscillation with no divergence, no
  negative-volume, no bounding failures** (ExecutionTime 335 s for 15 convective times). The
  `forces`/`forceCoeffs` FOs wrote through the motion; the loader parsed the real
  `coefficient.dat` / `force.dat` and the cycle-convergence guard fired correctly on the short
  run. The morpher holds well within the amplitudes Stage 11 needs.

### Consequences

- **Positive:** reuses the existing grids + `pimpleFoam`; boundary-layer-preserving; cheap;
  the overset fallback is real (libs present) and documented. Morphing validated on the SIF.
- **Negative:** morphing degrades at *large* amplitude / body-through-body motion — not a
  Stage-11 concern, but the flapping capstone (Stage 14+, large stroke) may need to escalate
  to overset. The escalation trigger is a `checkMesh` non-orthogonality/skew blow-up or a
  solver failure at the target amplitude.
- **Neutral / followup:** if a Stage-14 flapping case exceeds the morpher, add the
  `overPimpleDyMFoam` branch + an overset background+component mesh; the SIF already supports
  it. Robustness guards to carry forward: the **zero-amplitude regression** (a moving case at
  A=0 must reproduce the static Strouhal — catches a wrong `movingWallVelocity` frame) and a
  `checkMesh` at peak displacement.

## Pros and cons of considered options

### Option 1 — morphing (chosen)
- Good: near-wall + wake accuracy; reuses meshes + `pimpleFoam`; cheap; validated on the SIF.
- Bad: limited to small/moderate amplitude before mesh quality degrades.

### Option 2 — solidBodyMotionFvMesh
- Good: exact rigid motion, zero cell deformation.
- Bad: moves the external-flow far field/inlet → contaminates the force reference frame; wrong
  ergonomics for a body in a freestream.

### Option 3 — overset (fallback)
- Good: rigid body grid (no deformation) → handles arbitrarily large amplitude.
- Bad: overlap-interpolation adds wake dissipation + interpolation error; needs a
  background+component mesh + `overPimpleDyMFoam`; overkill (and less accurate) at A/D ≈ 0.2–0.5.

## Links

- Stage prompt: `docs/handoff-bundle/STAGE-11-moving-mesh-and-unsteady.md`
- Related ADR: ADR-017 (transient seed), ADR-019 (postprocess API), ADR-016 (FSI later)
- Governing scope: `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` §3.1
- External: OpenFOAM-ESI v2412 `oscillatingDisplacement` BC source (field = amplitude·sin(ωt));
  Placzek, Sigrist & Hamdouni (2009) *Comput. Fluids* 38:80–100 (forced-cylinder lock-in);
  Heathcote & Gursul (2007) *AIAA J* 45(5):1066–1079 (plunging-foil thrust).
