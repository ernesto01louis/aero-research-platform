# ADR-026 — CFD-in-the-loop optimizer: numpy GP+EI backend, NACA-4 parametrization, direct-CFD BO

- **Status:** accepted
- **Date:** 2026-07-10
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 15)
- **Stage:** 15 (CFD-in-the-Loop Airfoil Shape Optimization — re-targeted from flapping)
- **Supersedes:** none (first optimizer ADR; realises the ADR-013 mission)

## Context

Stage 15 is the mission: close the optimization loop and report the platform's first CFD-verified
improvement. The forward/UQ/provenance stack existed; the **optimization loop, the shape
parametrization, and the surrogate-of-the-objective were greenfield** (`aero/optimize/` did not
exist). Per the operator's mission pivot (2026-07-10) the demonstration is a **2-D airfoil shape
optimization** (the general-ASO vision; validates cleanly; cheap steady solves) rather than the
flapping wing (whose forward validation hit a 2-D-vs-3-D wall — Stage-14 NO-GO).

## Decisions

1. **Direct-CFD Bayesian optimization.** Every proposed design is evaluated by ground-truth CFD
   (Hard Rule 14 — no optimum on a surrogate prediction alone). A GP surrogate models the
   *objective over the design space* only to propose the next point (Expected Improvement); it never
   replaces the CFD verdict. The reported optimum is re-verified on a held-out CFD solve and
   `n_candidates` is recorded (selection-bias-aware, `OptimizationResult`).

2. **Backend: a lightweight pure-numpy GP + EI in `aero/optimize` core** (PLATFORM-NOT-HUB, Hard
   Rule 1 — the `import-platform-only.yml` fence). A Matérn-5/2 GP via `numpy.linalg.cholesky`
   (~40 lines) + closed-form Gaussian EI via `math.erf` (no scipy) — matching the platform's
   existing "EI via erf, no scipy in core" precedent. The design space is tiny (2–6 DVs) and the
   budget small (~15–30 CFD evals), the regime where a plain GP+EI is entirely adequate and
   BoTorch/Ax would be overkill. A `aero[bo]` extra is **reserved** for a BoTorch/Ax backend only
   when a later higher-dimensional space (FFD/SDF, Stage 17+) needs it.

3. **EI reimplemented, not imported from `aero/surrogates/_common/infill.py`.** That EI is ADR-025
   surrogate-in-the-loop machinery, present only on the concurrent feature branch (absent from
   `main`). Reimplementing the ~15-line closed form keeps `aero/optimize` self-contained and
   branch-independent. (Duplication of a trivial closed form is the lesser evil vs a cross-branch
   dependency; the two EIs may be reconciled when ADR-025 lands.)

4. **Shape parametrization: NACA-4 camber, y-only** (MVP 2-DV `{max_camber m, camber_position p}`,
   extensible to 3-DV `+ max_thickness_frac t` and to Hicks-Henne mode amplitudes). Thickness is
   applied normal to the chord on the SAME cosine x-stations (`geometry.py::naca4_coordinates`), so
   a shape change perturbs **y only** and the C-grid **mesh topology is invariant** — the invariant
   that makes matched-condition optimization deltas honest (correlated discretisation error cancels
   in the baseline↔candidate difference). Recovers NACA 0012 byte-identically at zero DVs; the
   `CaseSpec` shape fields are strict + bounded (frozen → provenance-faithful `config_hash`).
   Hicks-Henne (more general, needs a thickness-collision guard) is deferred but offered.

5. **Objective: maximize L/D = cl/cd at fixed AoA** on the trusted `laminar_airfoil` case (NACA 0012,
   Re=1000, steady laminar `simpleFoam` — the only green + reliably-converging + cheap airfoil V&V
   case), at a small positive AoA (~4°, well below the ~9° shedding onset) so there is lift and
   head-room to raise L/D by adding camber. Lift-constrained "minimize cd at fixed cl" needs an
   AoA-trim outer loop (not built) — deferred; a fixed-AoA L/D delta needs no new machinery.

6. **Delta-UQ: steady GCI-on-the-delta.** L/D is a STEADY scalar, so `u95_statistical = 0` and the
   whole delta uncertainty is the matched-grid Richardson on the L/D difference: solve baseline +
   optimum at ≥2 matched grids, difference per-grid, 2-grid GCI (Fs=3.0) on the delta series →
   `u95_delta_numerical`; compose via `compose_improvement(kind="steady")`. No paired-difference /
   cycle machinery (that is the unsteady flapping path, ADR-023).

## Considered options

- **BoTorch/Ax backend** — rejected for the MVP: heavy dependency tree (torch + gpytorch) that would
  have to live behind an extra; the 2–6-DV/15–30-eval regime does not need it. Reserved for Stage 17+.
- **Gradient-based / adjoint optimization (SU2)** — deferred (ADR-013 frozen-optional; the SU2 adjoint
  path is unplumbed). The post-v0.1.0 topology seed.
- **Hicks-Henne / CST / FFD parametrization** — deferred; NACA-4 camber is the cheapest, most
  interpretable first demonstration with an obvious physical win and exact baseline recovery.
- **Importing `infill.expected_improvement`** — rejected (branch dependency; see decision 3).

## Consequences

- **Positive:** `aero/optimize` is a self-contained, dependency-light optimizer that produces a
  CFD-verified, matched-condition, thesis-grade improvement delta reusing the entire existing
  reporting/UQ/provenance stack. The parametrization extends cleanly to more DVs and to Hicks-Henne.
- **Negative / limits:** the numpy GP uses a fixed length-scale (a coarse LML grid-search is a noted
  follow-up); the discrete-pool EI is adequate only in low dimension (a gradient/optimizer-based
  acquisition is a future need for higher-DV spaces); fixed-AoA L/D (not lift-constrained cd) is the
  MVP objective. All ledgered for Stage 16+.

## Links

- Realises ADR-013 (optimizer mission). Extends the UQ core (ADR-020/023) with the steady delta path.
- `aero/optimize/**`, `aero/adapters/openfoam/geometry.py::naca4_coordinates`,
  `aero/vv/reportable.py::OptimizationResult`, `.claude/rules/optimization-integrity.md`.
- Stage-15 prompt (re-targeted); external review F3 (prove the loop on a cheap trusted case).
