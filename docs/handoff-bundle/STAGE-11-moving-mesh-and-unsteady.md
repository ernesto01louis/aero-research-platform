# STAGE 11 — Moving-Mesh + Unsteady Post-Processing Toolkit

> Forward-capability track. Builds directly on the **Stage-10 transient seed**: a
> working `pimpleFoam` path + a lift-FFT Strouhal loader on a FIXED cylinder
> O-grid. Stage 11 makes the mesh *move* and turns unsteady traces into the
> derived quantities flapping needs (thrust, power, propulsive efficiency),
> rigorously (cycle-convergence + the groundwork for `u95_statistical`).

## BEFORE YOU START — READ

1. `CLAUDE.md` (auto-loaded) — esp. Hard Rules 12–17 + the optimizer-mission block.
2. `.aero-stage` (flip to `11` as this stage's first commit).
3. `docs/handoffs/STAGE-10-vv-debt-and-validity-bar-DONE-2026-06-15.md` — what
   Stage 10 delivered (3 forward-regime GOs + the transient seed) and deferred.
4. ADR-005 (TMR V&V), **ADR-017 (Stage-10 forward-regime + laminar/transient)**,
   ADR-013 (mission), ADR-015 (Invariant 10 — `u95_statistical` lands Stage 12).
5. `docs/handoff-bundle/README-handoff.md` (the Stage 10–20 map) +
   `.claude/rules/{flapping-validation-ladder,optimization-integrity}.md`.
6. Read first: `aero/adapters/openfoam/cylinder.py` (the transient O-grid +
   pimpleFoam case), `aero/adapters/openfoam/solver.py` (`run()` transient
   dispatch + the `_load_transient`/`_strouhal_from_signal` FFT path),
   `aero/vv/forward_regime/cylinder_strouhal.py`. Run to verify the world:
   `pytest tests/stage_10 tests/unit -q`, `mypy aero`, `ruff check aero tests`.

## Why this stage

The flapping mission is **unsteady and moving** (plunging/pitching/flapping
kinematics). Stage 10 proved the platform can run a transient OpenFOAM case and
recover a shedding frequency on a *static* body. Stage 11 adds (a) **mesh
motion** (the body moves) and (b) an **unsteady post-processing toolkit** that
turns Cl(t)/Cd(t)/p,τ traces into phase-averaged forces, thrust, power, and
propulsive efficiency — the quantities the optimizer's objective is built from —
with a **periodic-steady-state (cycle-convergence) check** so a reported number
is from a converged limit cycle, not a transient.

## Deliverables

1. **Moving-mesh solve path.** OpenFOAM `dynamicMotionSolverFvMesh` (rigid-body
   oscillation) — and AMI / `overPimpleDyMFoam` (overset) where prescribed motion
   needs it — pinned at v2412. Extend the adapter: a `dynamicMeshDict` writer and
   a moving-mesh run path (the `spec.transient` dispatch generalises to a motion
   spec). Reuse the Stage-10 O-grid + transient controlDict where possible.
2. **`aero/postprocess/` unsteady toolkit** (strict-pydantic, stdlib+numpy only —
   PLATFORM-NOT-HUB): phase-averaging over the shedding/forcing period;
   Strouhal/frequency (promote the Stage-10 `_strouhal_from_signal` FFT helper
   here, with parabolic peak interpolation); thrust / input power / **propulsive
   efficiency**; the **viscous/pressure force decomposition** (generalise the
   Stage-10 `forces`-FO loader so the split is a first-class typed output for any
   case); **periodic-steady-state detection** (cycle-to-cycle convergence of the
   force amplitude/mean).
3. **Moving-body V&V.** An **oscillating (transversely-forced) cylinder** and a
   **plunging airfoil** reproduce published Strouhal / lock-in (extend
   `aero/vv/forward_regime/` or a new `aero/vv/unsteady/`). Reference data
   DVC-tracked with a `reference.md` (the ladder's "unsteady machinery" tier —
   Heathcote-Gursul 2007 plunging-foil thrust is the natural anchor).
4. **NACA-rethink note (optional, time-permitting).** With the transient path in
   hand, the deferred NACA-0012 transient + time-averaged Cd (ADR-017 candidate)
   becomes feasible; if attempted, it is a transient-mean Cd vs the TMR value, and
   the result (GO or still-NO-GO) is documented — do not relax the 3% contract.
5. ADR for any new decision (motion-solver choice; the postprocess API). Post-stage
   handoff + author the Stage-12 prompt (`docs/handoff-bundle/STAGE-12-vv-uq-core.md`).
   Tag `v0.0.11`.

## The GO/NO-GO gate

**GO** = a moving-body case reproduces a published unsteady quantity (oscillating
cylinder lock-in Strouhal and/or plunging-airfoil thrust) within a stated
tolerance, **from a cycle-converged limit cycle**; the force decomposition closes
to the total within tolerance; the `aero/postprocess/` toolkit is typed + tested.

**NO-GO** = if moving-mesh cases cannot reach a periodic steady state or reproduce
the references, STOP and write up the root cause (motion solver, mesh-motion
quality, time resolution) before building Stage 12's UQ core on an untrusted
unsteady path. Tolerances are contracts.

*Scope note:* `u95_statistical` (batch-means / N_eff over the limit cycle) is
**Stage 12**, but Stage 11 must expose the cycle-convergence + sample machinery it
will consume. Transition (`kOmegaSSTLM`) is **Stage 13** — keep Stage-11 cases
laminar/inviscid-regime where possible.

## POST-STAGE HANDOFF (mandatory)

Write `docs/handoffs/STAGE-11-moving-mesh-and-unsteady-DONE-YYYY-MM-DD.md` with the
full frontmatter + 10 sections (`.claude/rules/handoff-discipline.md`). Emphasize:
the moving-mesh go/no-go (which cases pass, GCI/cycle-convergence evidence, MLflow
runs); the `aero/postprocess/` API; what the optimizer (Stage 15) will call. Confirm
the **Stage-12 prompt exists**. Then tag `v0.0.11`.
