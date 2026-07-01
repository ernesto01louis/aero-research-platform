# ADR-019 — `aero/postprocess/` unsteady toolkit API

- **Status:** accepted
- **Date:** 2026-07-01
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 11)
- **Stage:** 11
- **Supersedes:** none

## Context and problem statement

Stage 11 turns transient CFD traces (Cl(t), Cd(t), the `forces` FO history) into the derived
unsteady quantities the flapping optimizer's objective is built from — Strouhal/frequency,
phase-averaged loads, thrust / input power / propulsive efficiency, the viscous/pressure
force split, and a periodic-steady-state (cycle-convergence) check. The Stage-10 transient
seed scattered a slice of this (`_strouhal_from_signal`, the inline drag-decomposition
closure) inside the OpenFOAM adapter. Two forces shape where the new capability should live:

1. **PLATFORM-NOT-HUB** (Hard Rule 1): `aero/` core imports only stdlib + numpy + pydantic;
   solver specifics stay behind adapters.
2. **Stage 12 needs a seam.** The IMPROVEMENT-EXCEEDS-UNCERTAINTY invariant (Hard Rule 12)
   requires `u95_statistical` — the sampling error of a time/phase-average via batch-means /
   effective-sample-size *after a periodic-steady-state check* (`aero/vv/reportable.py`
   rejects a non-steady thesis-grade quantity with `u95_statistical == 0`). Stage 11 must
   expose the cycle-convergence + per-cycle-sample machinery Stage 12 will consume.
3. **The optimizer (Stage 15) calls it directly** — the objective (e.g. propulsive
   efficiency at fixed thrust) is computed from these functions, so the surface is public.

## Decision drivers

- Solver-agnostic (the optimizer and any solver's `load()` must reuse it).
- Typed + fail-loud (strict pydantic; a non-closing force split or a non-converged limit
  cycle must not silently produce a number).
- Minimal blast radius on the existing `Solver` ABC / `SolveResult` contract.
- A first-class, documented Stage-12 batch-means input.

## Considered options

1. **A standalone `aero/postprocess/` package of pure functions returning typed models;
   adapters call it and stuff scalars into `SolveResult.scalars`.** No ABC change.
2. **Extend the `Solver` ABC / `SolveResult`** with unsteady fields + a `postprocess()` seam.
3. **Keep it in the OpenFOAM adapter** (extend the Stage-10 inline helpers).

## Decision outcome

Chose **Option 1**: a standalone `aero/postprocess/` library (stdlib + numpy + pydantic),
six modules — `frequency`, `phase_averaging`, `forces`, `efficiency`, `cycle_detection`, and
the shared `_base` (`Signal`). Pure functions return strict-pydantic models; the OpenFOAM
adapter's `load()`/`_load_moving()` call them and write scalar outputs into
`SolveResult.scalars` (`strouhal`, `thrust_coefficient`, `propulsive_efficiency`,
`cycle_converged`, `n_converged_cycles`, `converged_from_cycle`, `mean_drift`,
`amplitude_drift`, `forcing_period`). **The `Solver` ABC is NOT changed.**

Key API decisions:

- **`Signal(t, y, name)`** is the unit the toolkit consumes and the unit Stage 12 builds on.
- **`segment_cycles` → `CycleSamples.per_cycle_mean`** is the **first-class batch-means
  seam**: it is computed by integrating over exactly one period with interpolated endpoints,
  so an oscillation's per-cycle mean is unbiased regardless of sample placement at the cycle
  boundary. Stage 12 restricts it to `[converged_from_cycle:]` for the N_eff estimate.
- **`ForceDecomposition`** makes closure (`pressure + viscous ≈ total`, 1e-3 + 1 % band) a
  **schema invariant** — the GO-gate "force decomposition closes to total" is now a validator,
  not a hand-rolled `if`. The Stage-10 adapter split routes through it (its file-pointing
  fail-loud message is preserved by wrapping the validator error).
- **`detect_cycle_convergence`** returns the longest settled tail (mean + amplitude drift
  within tolerance), robust to a zero-mean oscillation (mean drift normalised by the
  oscillation amplitude when the mean is negligible). `_load_moving` **raises** if the limit
  cycle has not converged — a non-converged number is not reportable (the NO-GO discipline).
- **`propulsive_metrics`** defines, for pure heave `y = h0 sin(ωt)` (matching OpenFOAM's
  `oscillatingDisplacement`, verified against the SIF BC source): thrust `C_T = -<F_x>/(½ρU²c)`,
  input-power `C_P = <-F_y·ẏ>/(½ρU³c)`, and `η = C_T/C_P` (None below the net-thrust
  threshold, so a St-sweep reports `C_T` through the sign change). Integer-cycle trapezoidal
  averaging.
- **No CLI group** — it is a library imported by the adapter, the V&V cases, and (later) the
  optimizer.

### Consequences

- **Positive:** solver-agnostic, PLATFORM-NOT-HUB-clean, host-testable on synthetic signals
  (36 Stage-11 unit tests). The Stage-12 statistical-U95 seam is a concrete, documented type
  (`CycleSamples`). Force-closure is enforced structurally. No churn to the `Solver` contract.
- **Negative:** the OpenFOAM-specific `force.dat` parsing (both layouts, full history) stays
  in the adapter, so a second solver wanting propulsion metrics must parse its own force file
  into arrays before calling `propulsive_metrics` — acceptable (the toolkit is array-in).
- **Neutral / followup:** Stage 12 wires `CycleSamples.per_cycle_mean` into the batch-means
  `u95_statistical` and the `small-signal-gate` CI; the phase-averaged waveform
  (`phase_average`) is available for LEV/wake visualisation but not yet consumed.

## Pros and cons of considered options

### Option 1 — standalone library, pure functions (chosen)
- Good: reuse by adapter + optimizer; core-clean; testable without a cluster; clean Stage-12 seam.
- Bad: solver-specific file parsing lives outside the toolkit (in the adapter).

### Option 2 — extend the Solver ABC / SolveResult
- Good: one object carries everything.
- Bad: couples the solver contract to unsteady concerns; every adapter/test touched; a bigger
  blast radius the mission doesn't need (ADR-008 set the precedent: don't amend the ABC until a
  second implementer forces it).

### Option 3 — keep it in the OpenFOAM adapter
- Good: least new code now.
- Bad: not reusable by the optimizer or another solver; not PLATFORM-NOT-HUB (the optimizer
  would import an adapter); no clean Stage-12 seam.

## Links

- Stage prompt: `docs/handoff-bundle/STAGE-11-moving-mesh-and-unsteady.md`
- Related ADR: ADR-017 (Stage-10 transient seed), ADR-015 (Invariant 10 — `u95_statistical`)
- Governing scope: `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` §3.4, §3.6
- Output-validity bar: `docs/vv/output-validity-bar.md`
