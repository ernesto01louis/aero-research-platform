# ADR-029 — Independent-RSS delta U95 for time-averaged claims without a common cycle basis

- **Status:** accepted
- **Date:** 2026-07-12
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 16)
- **Stage:** 16 (Grid-Converged Certification of the Airfoil Optimum)
- **Pairs with:** ADR-023 (paired-difference `u95_delta` — amended, not superseded), ADR-028
  (the graded family + steady NO-GO this path continues from), Hard Rule 12

## Context

ADR-023 made the delta's statistical term *measured, not asserted*: NOBM + τ_int on the
per-cycle **difference series** of a matched pair, which carries the shared cycle-to-cycle
covariance so the cancellation is measured. That estimator **requires a common cycle basis**
(matched periods to 1e-9 rtol, ≥8 common converged cycles) — built for the flapping path,
where baseline and candidate share the imposed kinematic period.

Stage 16's certification pair has **no common cycle basis**: the baseline (symmetric
NACA 0012 at AoA 4°) is steady, while the loaded optimum has resolved unsteadiness with no
imposed period. The paired estimator is category-inapplicable — there is nothing to pair on.
The existing schema offered only `ComposedDeltaU95` (paired REQUIRED for non-steady) or
`HandEnteredDeltaU95` (structurally never thesis-grade), so an honest, measured, unsteady,
unpaired delta had **no thesis-grade-admissible composition at all**.

## Decision

1. **`IndependentDeltaU95`** joins the `DeltaU95` discriminated union
   (`aero/vv/reportable.py`): `u95_numerical` (GCI on the time-averaged delta over the
   matched grid family) + two MEASURED `StatisticalUncertainty` terms (`baseline_stat`,
   `candidate_stat`, NOBM on time-weighted window means) + `u95_input`. Computed:
   `u95_delta_statistical = RSS(baseline, candidate)` and
   `u95_delta = RSS(numerical, statistical, input)`.
2. **No cancellation is claimed.** Matched runs correlate positively, so a true paired
   estimate would be *smaller*; the independent RSS is strictly conservative. This is the
   opposite failure mode of hand-entering: the composition can only over-state, never
   under-state, the uncertainty.
3. **Thesis-grade admissibility:** the gate accepts composed (ADR-023) OR independent
   (this ADR) measured variants; for the independent variant BOTH sampling estimates must be
   `reliable` (NOBM/τ_int agreement + N_eff floor). Hand-entered totals remain structurally
   barred. A steady claim with an independent U95 is a category error (fail-loud).
4. **Composition helpers:** `compose_independent_improvement()`
   (`aero/vv/reportable_compose.py`) builds the claim; `compose_independent_result()`
   (`aero/optimize/report.py`) is the URANS sibling of `compose_result` — GO iff FULL-RSS
   significance AND the family gates (stationarity of every claim solve, monotone delta,
   bounded observed order) pass, with a fail-loud check that the claimed values ARE the
   window means the sampling stats were measured on.
5. **Windows replace cycles:** `aero/postprocess/window_means.py` computes time-weighted
   (trapezoid) means over equal-duration windows of the adaptively-timestepped force series
   (sample means would bias toward small-dt intervals). The pre-registered stationarity gate
   per solve: half-tail drift ≤ 2× the full-tail sampling half-width, `reliable` NOBM, and
   positive window-mean cd in every window.

## Why not force the paired estimator

Padding the steady baseline into pseudo-cycles to satisfy the paired API would fabricate a
covariance structure that does not exist (the baseline series is iteration noise around a
steady value, not cycle samples of a shared forcing) — the measured "cancellation" would be
an artifact. ADR-023's own principle (measured, not assumed) demands refusing that.

## Consequences

- The flapping path is untouched: matched-period pairs keep using the (tighter) ADR-023
  composition. The independent variant exists for the genuinely unpaired case only, and its
  conservatism is the price of admissibility.
- `DeltaU95` consumers gain a third arm; pattern matches on the union were extended in the
  claim validator and the thesis-grade gate (tests pin all three arms' behavior).
