# Rule — Optimization integrity (CFD-verified optima; honest deltas)

## Scope

Loaded lazily when work touches `aero/optimize/`, the optimization loop, or any code that
reports a performance improvement. Operational form of Hard Rules 12
(IMPROVEMENT-EXCEEDS-UNCERTAINTY) and 14 (CFD-VERIFIED-OPTIMUM-ONLY). Guards the documented
AI-scientist failure modes (Luo, Kasirzadeh & Shah, arXiv:2509.08713: post-hoc selection
bias, metric misuse, data leakage).

## The contract

1. **CFD-verified optima only.** No optimum is reported on a surrogate prediction alone.
   Every reported optimum is re-evaluated with ground-truth CFD; the `OptimizationResult`
   carries the verifying run's four-tuple in its `cfd_verified` field. Exporting a result
   without it fails (Hard Rule 14; constitutional promotion at Stage 15).
2. **Improvement exceeds uncertainty.** A reported delta is thesis-grade only if
   `abs(delta) > k * u95_total` (default k = 2; never k < 1), where
   `u95_total = RSS(u95_numerical, u95_statistical, u95_input)` per
   `aero/vv/reportable.py`. GCI alone (numerical) is insufficient for unsteady quantities.
3. **Matched-condition deltas — cancellation is measured, not assumed (ADR-023).** Evaluate
   the baseline and the candidate at **identical numerics / mesh-topology** so correlated
   discretization and sampling errors cancel. The delta's statistical term comes from the
   paired-difference estimator (`aero/vv/paired_difference.py`): NOBM + τ_int on the per-cycle
   **difference series** over the common converged window. The empirical baseline↔candidate
   correlation and the `variance_reduction` ratio vs the independent RSS are recorded in the
   claim; `variance_reduction ≥ 1` means the cancellation failed and is surfaced, never hidden.
   `compose_improvement()` (in `aero/vv/reportable_compose.py`) assembles
   `u95_delta = RSS(GCI-on-the-delta, paired statistical, input)`.
4. **Selection-bias awareness.** When reporting "best of N" optimization candidates, the
   reported optimum is verified on a held-out CFD evaluation not seen by the optimizer, and
   the N (the number of candidates the best was selected from) is recorded — best-of-N
   selection inflates apparent performance.

## What NOT to do

- Do not report a surrogate's predicted optimum as a result (metric misuse).
- Do not compare a candidate's CFD against the baseline's surrogate value, or at different
  mesh resolutions (breaks correlated-error cancellation and leaks discretization bias into
  the delta).
- Do not claim an improvement whose delta is within its own U95 — that is numerical noise,
  not a result.
- Do not hand-enter `u95_delta` for a publication claim: `HandEnteredDeltaU95` is for
  exploratory tiers only and structurally cannot reach `thesis-grade` — a publication delta's
  uncertainty is composed via `compose_improvement()` from the paired-difference measurement
  (review F1; ADR-023).

## Why

The optimizer's only product is a *trustworthy* improvement. Closed-loop U95-gating of
optimization deltas is nascent in the literature — it is part of what makes this platform's
outputs thesis-grade, and it is the discipline that stops the loop from reporting noise or
hallucinated optima.
