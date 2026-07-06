# STAGE 14 — Rigid Flapping-Wing Validation

> Stage 13 made the platform's physics trustworthy in the transitional regime (`kOmegaSSTLM`
> verified on T3A) and resolved the unsteady-airfoil ladder rung. Stage 14 climbs to the
> **flagship forward capability**: a prescribed-kinematics **rigid flapping wing** at Re 10^2-10^4,
> validated against the canonical robotic-insect experiments (Dickinson 1999; Wang-Birch-Dickinson
> 2004). This is **the validated forward problem the optimizer runs on** (Stage 15, the thesis
> checkpoint) — it must clear its experiment anchor with a full U95 before the optimizer builds on it.

## BEFORE YOU START — READ

1. `CLAUDE.md` (auto-loaded) — invariants; esp. Hard Rule 15 (VALIDATE-AGAINST-EXPERIMENT), the
   four-fold provenance, and the U95 machinery (Stage 12).
2. `.aero-stage` (flip to `14` as this stage's first commit).
3. `docs/handoffs/STAGE-13-transition-and-unsteady-airfoil-DONE-*.md` — the transition pin +
   the unsteady-airfoil resolution; the reusable moving-mesh + U95 seams.
4. `.claude/rules/flapping-validation-ladder.md` (Stage-14 rung: **rigid** revolving/flapping wing
   vs Dickinson 1999 Robofly + Wang-Birch-Dickinson 2004) + `optimization-integrity.md`.
5. `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` (§3.1 moving-mesh, §3.6 unsteady post-proc, §4
   validation ladder) + `README-handoff.md` (the Stage 10-20 map).
6. ADR-018 (moving-mesh motion solver), ADR-019 (unsteady postprocess API), ADR-021/022 (the
   Stage-13 transition + unsteady-airfoil decisions).

## Why this stage

Flapping-wing aerodynamics is the flagship demonstration domain (`00-MISSION-AND-SCOPE.md` §1.3):
broad, underexplored, LEV-dominated. The Stage-11 moving-mesh toolkit did pure **heave** (a
plunging airfoil); a flapping wing adds **rotation** (pitch about a spanwise axis) combined with
translation/revolution — the stroke kinematics that generate the leading-edge vortex and the
delayed-stall lift that insects exploit. Reproducing the measured force traces (and the LEV) on a
**rigid** wing is the last forward-capability rung before the optimizer: it validates the moving-
mesh + kinematics + low-Re-transitional physics on the actual mission geometry.

## Deliverables

1. **Flapping kinematics in the OpenFOAM adapter.** Prescribed combined translation/revolution +
   pitch (the new angular-motion primitive the Stage-13 handoff deferred): a `PitchMotionSpec` /
   flapping-stroke motion + the `angularOscillatingDisplacement` (or solid-body `rotatingMotion`)
   pointDisplacement/dynamicMesh path in `aero/adapters/openfoam/motion.py`. Pin the motion-solver
   choice (mesh-deformation vs overset) in an ADR — the large stroke amplitude may exceed what the
   `displacementLaplacian` morph tolerates (consider `overPimpleDyMFoam` overset, ESI v2412).
2. **Rigid flapping-wing V&V case(s).** A 2-D (or quasi-3-D revolving) rigid wing at Re 10^2-10^4,
   laminar/incompressible (the transitional path from Stage 13 available if the regime warrants),
   validated against **Dickinson et al. (1999)** Robofly lift/drag vs stroke phase and/or
   **Wang, Birch & Dickinson (2004)** (2-D vs 3-D, quasi-steady vs unsteady). Acquire the reference
   data DVC-tracked under `data/references/flapping/<case>/` with a `reference.md` (citation,
   license, digitization provenance, u95_input) — a Stage-14 acquisition item (deferred-work ledger).
3. **Full-U95 `ReportableResult`** on the flapping force trace: cycle/phase-averaged lift (and/or
   the stroke-averaged coefficients) with `u95_statistical` (batch-means over converged cycles) +
   `u95_numerical` (space+time GCI, `scripts/stage13_gci.py` pattern) + `u95_input`, composed via
   `scripts/stage13_reportable.py` (generalize as needed). Clear the experiment anchor within a
   pre-declared honest band (never relaxed).
4. **LEV capture evidence.** Phase-averaged vorticity / Q-criterion snapshots over the stroke
   showing the leading-edge vortex forming + shedding — the qualitative signature the force trace
   quantifies.
5. ADR(s) for the flapping-kinematics + motion-solver decisions. Post-stage handoff + author the
   **Stage-15 prompt** (`docs/handoff-bundle/STAGE-15-cfd-in-the-loop-optimization.md` — the THESIS
   CHECKPOINT: parametric CFD-in-the-loop optimization, CFD-verified delta > k*U95). Tag `v0.0.14`.

## The GO/NO-GO gate

**GO** = the flapping-kinematics moving-mesh path runs stably through >= 1 converged stroke cycle,
AND a rigid flapping-wing force trace carries a full RSS-composed `U95` into a `ReportableResult`
that clears its Dickinson/Wang experiment anchor within a pre-declared band, WITH LEV capture
evidence. This is the validated forward problem the Stage-15 optimizer runs on.

**NO-GO** = if the flapping-kinematics mesh motion cannot sustain a stroke without mesh failure, or
the force trace cannot be brought within band, STOP and document — the optimizer (Stage 15) must
not build on an untrusted flapping forward model. Investigate the physics (mesh motion, Re,
kinematics fidelity, 2-D-vs-3-D), never relax the tolerance.

## Infra + conventions (unchanged from Stage 13)

Storage NAS-NFS at `/mnt/aero` (host `/mnt/aero-nfs`). Solver SIFs run as LXC root on `aero-dev`
(16 cores; `aero-vv` has no apptainer). MPI is BLOCKED in the LXC -> OpenFOAM runs SERIAL; moving
solves exceed the 30-min executor ceiling -> run via a long-timeout DETACHED driver
(`scripts/stage11_moving_vv.py` is generic over `UNSTEADY_CASES` / a new `FLAPPING_CASES` registry),
poll `/mnt/aero/runs`. Independent serial jobs may be run concurrently on the 16-core box (not MPI
-> no approval needed); genuine parallel/privileged is propose-first (`approved`). COMMIT GOTCHAS:
`source .venv/bin/activate` before `git commit`; a shebang'd script must be `chmod +x`; NEVER
`--no-verify`; `main` is branch-protected -> branch + PR; Conventional Commits scoped
`<type>(stage-14)`, header <= 100 chars; the `moving` marker excludes multi-hour cases from
`vv-required`. Vault (LXC 217) is SEALED — note, don't work around.

## POST-STAGE HANDOFF (mandatory)

Write `docs/handoffs/STAGE-14-rigid-flapping-wing-DONE-YYYY-MM-DD.md` (full frontmatter + 10
sections, `.claude/rules/handoff-discipline.md`). Emphasize: the flapping-kinematics + motion-solver
pin; the rigid flapping-wing force validation with the composed U95; the LEV capture evidence.
Confirm the **Stage-15 prompt exists**. Tag `v0.0.14`.
