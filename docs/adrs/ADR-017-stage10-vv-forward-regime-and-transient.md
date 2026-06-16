# ADR-017 — Stage-10 V&V: NACA blunt-TE rejected; forward-regime laminar/transient cases

- **Status:** accepted
- **Date:** 2026-06-16
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 10)
- **Stage:** 10
- **Supersedes:** none (refines ADR-005 TMR V&V harness, ADR-012 blunt-TE pass)

## Context and problem statement

Stage 10 is the HARD V&V go/no-go gate. The forward solver carried three failing
turbulent NASA-TMR cases (ADR-005), and — per ADR-013 — the mission is a low-Re
flapping-wing optimizer, whose flow regime (Re ~ 10²–10⁴, laminar/transitional,
unsteady) the all-turbulent TMR set does not exercise at all. Stage 10 must both
retire what it can of the turbulent debt and add canonical cases in the mission's
own regime (the flapping-validation ladder's "forward-regime credibility" tier).

The Stage-09 fix for the headline NACA 0012 +21% Cd error was a **blunt-TE
C-grid**, built but never cluster-validated.

## Decision drivers

- Tolerances are contracts (never relaxed); a case is a GO only if it genuinely
  passes, else a documented NO-GO with root cause (stage prompt).
- The optimizer mission depends on the *forward-regime* cases, not the turbulent
  table-stakes (effort-allocation per SCOPE-GATE / Hard Rule 17).
- "A turbulent case that proves an off-regime deep mesh-craft rabbit hole is
  itself a rethink trigger to bring to the operator" (stage prompt).
- PLATFORM-NOT-HUB / FAIL-LOUD / provenance-from-day-one still hold.

## Considered options

1. **Force the NACA blunt-TE C-grid to pass** — keep iterating mesh/numerics
   until Cd < 3%.
2. **Reject the blunt-TE remedy; document NACA as a NO-GO; add forward-regime
   laminar + transient cases** (the regime the mission needs).
3. **Skip the forward-regime cases this stage** — only chase the turbulent debt.

## Decision outcome

Chose **Option 2**.

**NACA 0012 blunt-TE C-grid is REJECTED** as the remedy. A pre-cluster
adversarial validation found four blockers (non-conformal base-wake grading; a
collapsed-prism zero-area face; an invalid base wall function; no drag
decomposition); all were fixed to a checkMesh-valid mesh, but the steady solve
still **does not converge** — after tapering the base wake to the sharp-baseline
aspect ratio, `simpleFoam` ran ~83 stable iterations then a momentum/pressure
blow-up while turbulence stayed converged, the signature of the **finite blunt
base's inherently unsteady (shedding) wake defeating a steady-state solver**.
A closed-form budget also shows blunt-TE cannot reach 3% even converged (friction
held fixed, base drag additive). NACA 0012 stays xfail with an evidence-based
reason; resolution is deferred to a rethink (transient + time-average, a sharp-TE
TE-region remesh, or an SU2 cross-check).

**Three forward-regime canonical cases were ADDED and are GREEN:**

| Case | Regime | Reference | Result |
|---|---|---|---|
| `blasius_flat_plate` | steady laminar | Blasius Cf = 0.664/√Re_x (exact) | GO, Cf 2.15% |
| `laminar_airfoil_naca0012` | steady laminar, Re=1000 | Kurtuluş (2015) Cd + Cl=0 symmetry | GO, Cd 0.16%, Cl 0.23% |
| `cylinder_strouhal_re100` | **transient** laminar shedding | Roshko/Williamson St≈0.165 | GO, St 4.0% |

To support them, two adapter capabilities were added:

- **Laminar solve path** — `turbulence_properties` gains a `simulationType
  laminar` branch; `CaseSpec`/`FlatPlateSpec` accept `turbulence_model="laminar"`;
  the field writers emit only U and p (no k/omega/nut). Turbulent paths unchanged.
- **Transient path (first unsteady OpenFOAM case)** — `CylinderSpec` +
  `write_cylinder_case` (a 4-block O-grid, `pimpleFoam`, Euler/PIMPLE,
  adjustable timestep); `OpenFOAMSolver.run()` dispatches `pimpleFoam` for
  `spec.transient`; a transient `load()` branch FFTs the Cl(t) tail (parabolic
  peak interpolation) → `scalars["strouhal"]` with a `TimeHistory`. This
  pre-empts a slice of the Stage-11 unsteady machinery, by design (the flapping
  mission is unsteady).

### Consequences

- **Positive:** the mission-critical low-Re regime is validated (3 GREEN cases,
  incl. the first transient case); a reusable laminar + transient OpenFOAM
  capability now exists; the NACA NO-GO is honestly characterised, not papered
  over.
- **Negative:** NACA 0012 remains a documented NO-GO (turbulent table-stakes);
  the blunt-TE C-grid code is retained but rejected as the remedy.
- **Neutral / followup:** transient time-averaging, a U95 envelope on the
  unsteady St (`u95_statistical`, ADR-015 Invariant 10), and the NACA rethink
  are Stage-11+/12 work. The cylinder St (4%) would tighten with a longer run.

## Pros and cons of considered options

### Option 1 — force blunt-TE to pass
- Good: would close the headline turbulent debt.
- Bad: three cluster solves proved the steady solver cannot converge a shedding
  blunt base; deeper mesh-craft is the rabbit hole the stage prompt warns against,
  and the arithmetic shows it cannot pass 3% regardless.

### Option 2 — reject blunt-TE; add forward-regime cases (chosen)
- Good: invests effort where the mission needs it; honest NO-GO; new capabilities.
- Bad: leaves a turbulent table-stakes case unresolved (documented, deferred).

### Option 3 — skip forward-regime cases
- Good: less new code.
- Bad: leaves the solver unvalidated in the mission's actual flow regime —
  the opposite of the stage's intent.
