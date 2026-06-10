# STAGE-11: preCICE 3 Coupling & FSI Demo

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"Coupling" and Pass 1 §"Multi-physics coupling":

- preCICE 3.x deployed via the preCICE distribution v2404+ (Apptainer SIF).
- `aero/adapters/precice/` providing FSI orchestration on top of the Stage 06
  `Solver` protocol.
- One canonical FSI benchmark working end-to-end with full provenance:
  the Turek-Hron FSI3 benchmark (laminar flow around an elastic flap) using
  OpenFOAM (fluid) coupled to CalculiX (structure) via preCICE.
- The architectural foundation for the later research directions: flapping-wing
  aerodynamics, vibrating-skin drag reduction, conjugate heat transfer.

## ROLE

You are adding multi-physics coupling — the first time the platform runs more
than one solver simultaneously in a coupled scheme. The preCICE library is the
proven SOTA for partitioned coupling in open-source CFD (Pass 1 confirms; the
preCICE site documents v3 improvements for large meshes). Your job is to wire
it up cleanly without compromising the `Solver` protocol.

## GOAL

1. Author `containers/precice-distribution.def` — Apptainer SIF built on the
   official preCICE distribution v2404+ Ubuntu 24.04 packages. Includes
   `libprecice3`, `pyprecice`, the OpenFOAM-preCICE adapter, the CalculiX-preCICE
   adapter, and CalculiX itself.
2. Build, sign, append SHA.
3. Author `aero/adapters/precice/`:
   - `coupler.py` — `PreciceCoupler` class that takes two `Solver` instances and
     a `CouplingSpec` (pydantic), runs them via preCICE
   - `schemas.py` — `CouplingSpec` (data mapping, exchange directions, time-
     stepping scheme, acceleration: IQN-IMVJ or Aitken)
   - `runtime.py` — coordinates the two processes via preCICE's runtime
4. Add `aero[precice]` extras: `pyprecice`, plus the structure-solver Python
   bindings if available.
5. Implement the Turek-Hron FSI3 benchmark at `aero/vv/fsi/turek_hron_fsi3/`:
   - Fluid case: OpenFOAM `pimpleFoam`, laminar, Re=200
   - Structure case: CalculiX with St. Venant–Kirchhoff material
   - Coupling: implicit, IQN-IMVJ acceleration
   - Reference data: published time-averaged flap-tip displacement and
     hydrodynamic loads from Turek & Hron 2006 (canonical)
6. Run the case end-to-end; verify the time-averaged tip displacement matches
   the published reference within 5%. Log the four-tuple to MLflow.
7. Add `aero/vv/fsi/` to the V&V harness; add `vv-fsi.yml` workflow (nightly,
   not PR-gating — FSI cases are slow).
8. Author `aero/cli.py` additions: `aero fsi run --case turek_hron_fsi3`.
9. Sketch (do NOT implement) the future research directions in
   `docs/architecture/fsi-roadmap.md`:
   - Flapping-wing: OpenFOAM + structure solver, prescribed kinematics first,
     then learned actuation
   - Vibrating-skin riblets: small-amplitude high-frequency, requires
     specialized time-stepping
   - Conjugate heat transfer: OpenFOAM + CalculiX thermal
   These are research, not platform-building; the doc just notes that the
   coupling layer supports them.
10. Author ADR-011 documenting:
    - preCICE 3 vs alternatives (MUI, MpCCI) — why preCICE
    - The Turek-Hron benchmark choice (canonical, well-documented, small)
    - Implicit IQN-IMVJ over Aitken (better convergence for strong coupling)
    - The deferred FSI research roadmap
11. Update CLAUDE.md with the FSI workflow conventions.
12. Tag `v0.0.11`.

## WHY

Multi-physics coupling is the gateway to a large fraction of the user's
research interests: flapping-wing, vibrating-skin drag reduction, conjugate
heat transfer. Without it, the platform only does single-physics aero.

preCICE 3 is the open-source SOTA for partitioned coupling (Pass 1, Pass 2).
The distribution package ships everything in compatible versions, which is the
correct way to install it on a fresh system (per the preCICE site).

Turek-Hron FSI3 is the canonical benchmark — every preCICE paper uses it,
every adapter is tested on it. Reproducing it is the proof that our coupling
layer works correctly.

## HOW

- preCICE distribution: install via `apt` from the official `.deb` repo
  inside the SIF. Pin to a specific distribution release (e.g., v2404).
- The `PreciceCoupler` runs both solvers in separate processes; preCICE
  handles the synchronization. Use Python's `multiprocessing` or two SSH
  invocations on the same LXC.
- For CalculiX: pyCalculiX bindings exist; otherwise drive the binary via
  subprocess. The adapter writes `precice-config.xml` from `CouplingSpec`.
- Reference data: Turek-Hron paper (Turek & Hron 2006, "Proposal for numerical
  benchmarking of fluid-structure interaction between an elastic object and
  laminar incompressible flow") — extract the time-averaged tip displacement
  and lift/drag.
- Implicit coupling iteration count: IQN-IMVJ typically converges in 4-8
  iterations per time step for FSI3.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-11-precice-coupling-and-fsi.md` (this file)
- `docs/handoffs/STAGE-10-*-DONE-*.md`
- ADR-006, ADR-007, ADR-008
- Pass 1 §"Multi-physics coupling"
- Pass 2 §1 (RANS-LES SOTA — relevant for FSI flow side)

## GUARDRAILS — DO NOT

1. Do NOT build preCICE from source if the distribution package works. The
   distribution is the supported install path.
2. Do NOT skip the IQN-IMVJ acceleration. Explicit coupling on FSI3 diverges.
3. Do NOT implement flapping-wing or riblets here. That's research, deferred to
   post-v0.1.
4. Do NOT compromise the `Solver` protocol to fit preCICE's needs. The
   `PreciceCoupler` consumes two `Solver` instances; preCICE-specific
   complexity stays inside the coupler.
5. Do NOT log only the fluid-side provenance. The structure side gets its own
   four-tuple; the coupling case has a combined tuple covering both.

## DELIVERABLES

- [ ] preCICE-distribution SIF builds; SHA in SHA256SUMS
- [ ] `pip install -e .[precice,openfoam,dev]` works
- [ ] Turek-Hron FSI3 case runs end-to-end via `aero fsi run --case
      turek_hron_fsi3`
- [ ] Time-averaged tip displacement within 5% of Turek-Hron 2006 reference
- [ ] Per-solver provenance four-tuples logged plus combined coupling tag
- [ ] `vv-fsi.yml` nightly workflow active
- [ ] `docs/architecture/fsi-roadmap.md` sketches deferred research
- [ ] ADR-011 committed
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.11`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- The preCICE distribution version pin
- CalculiX as the structure solver (alternatives: deal.II, FEniCS — propose if
  preferred)
- Marking the FSI nightly workflow as required check (do NOT — too slow)

## POST-STAGE HANDOFF

Required emphases:

- **FSI3 numbers**: tip displacement amplitude and frequency, hydrodynamic
  loads, vs reference.
- **Coupling iteration counts and wall-clock** per time step.
- **The combined provenance tag**: how it's structured.
- **Open items for Stage 12**: FSI is part of the full V&V scope; flag any
  preCICE-side V&V additions needed.
- **Gotchas**: preCICE-config XML quirks, adapter-version compatibility,
  process-coordination races.
