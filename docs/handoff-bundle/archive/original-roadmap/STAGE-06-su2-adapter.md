# STAGE-06: SU2 Adapter — Forcing the Abstraction

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"Solver fleet" and Pass 1 §"Physics & solver layer":

- SU2 v8 adapter as the second concrete `Solver` implementation.
- The `Solver` interface generalized **based on what SU2 forces**, not
  speculatively.
- All TMR V&V cases now run through both OpenFOAM AND SU2; cross-solver comparison
  reports are produced.
- Compressible/transonic capability added (NACA 0012 transonic, ONERA M6).
- SU2-NEMO + Mutation++ pinned as the future-hypersonic path (built, not yet
  exercised — full hypersonic test is research, not platform-building).
- The "platform-not-hub" invariant is now structurally enforced: `aero[su2]` is
  optional; base install of `aero` works without SU2.

## ROLE

You are adding the second concrete solver to force the right shape of abstraction.
You will NOT generalize speculatively; you will refactor the OpenFOAM adapter
and the SU2 adapter together until both implement a clean shared protocol.
Pass-3 best-practices guidance is explicit: the second concrete implementation
is what reveals the right abstraction.

## GOAL

1. Author `containers/su2-v8.def` — Apptainer SIF based on SU2 v8.x source build,
   with Python wrapper enabled, mpi4py, autodiff enabled, Mutation++ included (for
   future hypersonic). Pin the SU2 git tag.
2. Build the SIF; sign; append SHA256.
3. Author `aero/adapters/su2/`:
   - `solver.py` with `SU2Solver` implementing the same shape as `OpenFOAMSolver`
   - `schemas.py` with SU2-specific `CaseSpec` extensions (Mach, AoA, mesh
     format)
4. Generalize the `Solver` protocol at `aero/adapters/_base.py`:
   - Extract what both implementations share (prepare/mesh/run/load lifecycle,
     provenance hook, executor injection)
   - Move solver-specific behavior to abstract methods or strategy classes
   - The shape is decided by the *intersection* of OpenFOAM and SU2 needs, not
     by anticipation of PyFR/NekRS/JAX-Fluids (those come in Stages 07–08 and
     will trigger further refactor if needed — that's fine)
5. Refactor the OpenFOAM adapter to implement the new `Solver` protocol. Both
   adapters now share the base class. Tests still pass; no behavior change.
6. Add `aero[su2]` extras: `mpi4py`, `meshio` (for SU2 native mesh format),
   compatible numpy.
7. Re-implement the three TMR cases for SU2 in `aero/vv/tmr/` (the cases stay,
   but each case can now be run by either solver via an executor flag). Each
   case has reference data; both solvers should produce results within the
   same tolerance bands.
8. Add two transonic cases (compressible):
   - NACA 0012 transonic, Mach 0.7, AoA 1.49° (Cd from AGARD AR-138 reference
     or similar)
   - ONERA M6 wing, Mach 0.84, AoA 3.06° (canonical transonic wing benchmark)
   These live under `aero/vv/transonic/` (new directory) and use SU2 as primary
   solver. OpenFOAM `rhoCentralFoam` is available as a cross-check.
9. Author `aero/vv/cross_solver_compare.py`:
   - For each case, runs both solvers, computes the cross-solver discrepancy
     per metric, flags any case where the two solvers disagree by more than the
     V&V tolerance
   - Produces a cross-solver comparison report (markdown + JSON), stored as an
     MLflow artifact and linked from the V&V dashboard
10. Update `vv-smoke.yml` to run both OpenFOAM and SU2 paths for the TMR cases.
    Add the transonic cases to a separate `vv-transonic.yml` workflow (slower;
    nightly only, not PR-gating).
11. Author ADR-006 documenting:
    - The `Solver` protocol shape and what each adapter implements
    - Why SU2 was chosen as the second solver (compressible, adjoint, hypersonic
      future) over Code_Saturne or others
    - The SU2 version pin and the Mutation++ inclusion
12. Update `CONSTITUTION.md` if any new invariants emerged from the
    generalization (e.g., "all solvers expose convergence history as a typed
    series").
13. Verify the "platform-not-hub" invariant: `pip install aero` (no extras) in a
    fresh venv must import cleanly. Add a CI job `import-platform-only` that
    asserts this.
14. Tag `v0.0.6`.

## WHY

Single-solver abstractions are wrong by default. Until the second solver lands,
the `Solver` interface in `aero/adapters/_base.py` is just a thin restatement of
the OpenFOAM adapter. SU2 forces the truth: meshing pipelines differ, BC
specification differs, convergence semantics differ, parallel-execution
launching differs. The right shape emerges from the intersection.

Compressible capability unlocks half the aerodynamics domain (transonic and
above). Without it, the platform serves only low-Mach external aero — a
fraction of the thesis-relevant scope.

The Mutation++ inclusion costs almost nothing now (a couple hundred MB of SIF)
and unlocks SU2-NEMO hypersonic work later without revisiting the container
build. Future-proofing where it's cheap is fine; future-proofing where it's
expensive (e.g., guessing the agent layer's shape) is not.

## HOW

- SU2 v8 build: long. Use `tmux` long-running pattern. ~30-60 minutes on the
  build LXC depending on flags.
- The `Solver` base class: prefer Python `Protocol` (PEP 544) over ABC where
  practical; pydantic for typed shared schemas. Generic over the executor type if
  it cleans up.
- SU2 native mesh format is `.su2`; OpenFOAM is polyMesh directory. Use
  `meshio` for cross-conversion where needed. Each adapter handles its own mesh
  format internally; the platform CaseSpec is mesh-format-agnostic above the
  adapter level.
- For transonic NACA 0012: use the AGARD AR-138 case 1, or equivalently the
  Schmitt/Charpin experimental data. Cite the reference in the case directory's
  README.
- For ONERA M6: standard reference is Schmitt/Charpin (ONERA TR No. 1) and
  pressure data is in the SU2 tutorial repo (BSD; copyable).
- Cross-solver comparison: don't try to make the two solvers' meshes identical
  (impossible — different mesh formats and refinement strategies). Compare
  output quantities (Cd, Cp at fixed x-locations) at converged states, not
  intermediate fields.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-06-su2-adapter.md` (this file)
- `docs/handoffs/STAGE-05-*-DONE-*.md`
- ADR-003 (walking skeleton's out-of-scope list — Stage 06 lifts the
  "multi-solver abstraction" item)
- ADR-004, ADR-005
- Pass 1 §"Physics & solver layer" for SU2 rationale and scope

## GUARDRAILS — DO NOT

1. Do NOT generalize speculatively for PyFR/NekRS/JAX-Fluids in this stage.
   Generalize from the intersection of OpenFOAM and SU2 only.
2. Do NOT regress any TMR tolerance from Stage 05. The OpenFOAM path's numbers
   must be unchanged after the refactor.
3. Do NOT make `aero[su2]` install pull in `aero[openfoam]` or vice versa.
   They are independent extras.
4. Do NOT skip the `import-platform-only` CI check. The platform-not-hub
   invariant must be structurally enforced.
5. Do NOT mix SU2 with OpenFOAM in a single case via shell scripting tricks.
   Each case is run by one solver; cross-solver compares produce a third
   artifact (the comparison report).
6. Do NOT include any closed-source dependencies in the SU2 SIF (no Intel MKL
   for production builds — use OpenBLAS or equivalent; document the choice
   in the ADR).

## DELIVERABLES

- [ ] `containers/su2-v8.sif` builds and SHA appended to SHA256SUMS
- [ ] `pip install -e .[su2,dev]` succeeds in a fresh venv
- [ ] `pip install -e .` (no extras) imports cleanly — verified by
      `import-platform-only` CI job
- [ ] All three TMR cases pass via SU2 within the same tolerances as OpenFOAM
- [ ] OpenFOAM TMR numbers unchanged after refactor
- [ ] Two transonic cases pass against reference (Cd within 5%, Cp within 5%)
- [ ] Cross-solver comparison report produced for each TMR case and posted to
      MLflow
- [ ] `tests/stage_06/` and `tests/vv/` green
- [ ] `vv-transonic.yml` nightly workflow active
- [ ] ADR-006 committed
- [ ] CONSTITUTION updated if needed
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.6`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- The SU2 v8 specific tag/commit to pin (operator may have institutional
  preference)
- The shape of the `Solver` base class — propose the protocol, get sign-off,
  then refactor both adapters
- Adding the transonic cases to nightly CI (they're slow)
- Any change to TMR tolerances from Stage 05

## POST-STAGE HANDOFF

Required emphases:

- **The `Solver` protocol final shape** — link to `aero/adapters/_base.py`,
  explain each method.
- **Refactor diff stats**: which OpenFOAM-adapter methods moved up, which
  stayed local.
- **Cross-solver discrepancy numbers** for the three TMR cases.
- **Open items for Stage 07**: PyFR and NekRS will further test the abstraction;
  flag any seams that already look fragile.
- **Gotchas**: SU2 Python wrapper quirks, Mutation++ runtime symbol issues if
  any, mesh-format conversion edge cases.
