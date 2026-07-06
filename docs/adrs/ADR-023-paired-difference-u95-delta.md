# ADR-023 — Paired-difference `u95_delta`: Invariant 10 enforcement now COMPUTES the delta uncertainty

- **Status:** accepted (the design); carries a **proposed** one-sentence CONSTITUTION amendment
  (see "Constitution amendment" below — separate PR, 72 h window per the amendment process)
- **Date:** 2026-07-06
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (review-F1 remediation,
  between Stages 13 and 14)
- **Stage:** 13 (inter-stage; review remediation)
- **Supersedes:** none (extends ADR-020's UQ core)

## Context and problem statement

The 2026-07 external technical review (`docs/review/2026-07-external-review.md`, finding **F1** —
its most important finding) showed that the platform's flagship guarantee was hollow at its
center: `ImprovementClaim.u95_delta` was a **free input field**. The validator asserted
`delta > k * u95_delta` and the required `small-signal-gate` CI job re-ran that assertion — but
nothing anywhere computed `u95_delta`, and CONSTITUTION Invariant 10's matched-condition
correlated-error cancellation ("the uncertainty of the delta is then below the RSS of the two
absolute uncertainties") was asserted in prose, never measured. At Stage 15 the headline result
would have reduced to *"the delta exceeds k times a value the author supplied."*

## Decision drivers

- **FAIL-LOUD / unconstructibility.** Invariant 11's precedent: a foreign + validated certificate
  is unconstructible. The same mechanism should make a hand-typed `u95_delta` unable to reach
  `thesis-grade`.
- **Reuse, don't duplicate.** Stage 12's NOBM + tau_int estimator
  (`aero/vv/statistical_uncertainty.py`) is validated against known answers; the delta machinery
  must run *through* it, not beside it.
- **PLATFORM-NOT-HUB.** stdlib + numpy + pydantic only; the GCI-on-the-delta arrives absolute from
  the caller (the `compose_reportable` seam), keeping runner imports out of `aero/vv/`.
- **Honest small-N statistics.** The paired window is O(20–40) cycles; the estimator must inherit
  the existing small-sample honesty (Student-t, soft `reliable` flag, hard NO-GOs).
- **Auditability.** The review demands the empirical baseline↔candidate correlation be *recorded*,
  so failed cancellation surfaces instead of hiding inside a hand-entered number.

## Considered options

1. **Status quo + documentation** — keep the free float, document that callers should compute it.
2. **A `source` tag string beside the float** — records provenance but the float stays free; a tag
   is exactly as forgeable as the number it decorates.
3. **Discriminated union with embedded evidence** (`HandEnteredDeltaU95 | ComposedDeltaU95`, the
   composed arm carrying the typed paired-difference measurement) — **chosen**.
4. **Always-computed, no hand path** — kills `smoke`/`validated`-tier exploratory claims, and
   steady deltas legitimately have caller-supplied-only numerics.
5. **Analytic covariance composition** `u_delta^2 = u_b^2 + u_c^2 - 2*rho*u_b*u_c` — statistically
   rejected: fragile degrees-of-freedom bookkeeping at NOBM's batch counts, and it double-counts
   what the difference series already measures directly.

## Decision outcome

Chose **Option 3**. Three pieces:

### 1. The estimator — `aero/vv/paired_difference.py`

`paired_delta_uncertainty(baseline, baseline_report, candidate, candidate_report)` takes the two
runs' `CycleSamples` + `CycleConvergenceReport`, verifies both converged and the **periods match
to 1e-9 rtol** (matched runs share one motion spec — any real mismatch means index pairing is
physically meaningless), forms the **intersection window** `[max(converged_from_cycle),
min(n_cycles))` (cycle *k* is the same physical forcing cycle in both runs; each-side-own-tail
trimming would silently pair different cycles), and delegates to
`paired_delta_uncertainty_from_samples`, which runs the **existing** NOBM + tau_int machinery
three times over the SAME window: per-side baseline, per-side candidate, and on the **difference
series** `candidate - baseline`. The result is `PairedDeltaUncertainty` (strict frozen):

- `u95_delta_statistical` = the difference-series half-width — the **measured** post-cancellation
  statistical uncertainty (whatever covariance the runs share is in the diff by construction);
- `correlation` (empirical Pearson r) + `variance_reduction`
  (= `u95_delta_statistical / RSS(u95_b, u95_c)`) — the **audit trail**; weak/anti-correlation
  gives `variance_reduction >= 1`: surfaced, honest (wide), never a raise;
- cross-field validators pin the embedded stats to the window and to each other (n_samples ==
  n_pairs, `u95 == t*se`, means match) and refuse a per-side `u95 == 0` (zero denominator).

Fail-loud paths (`PairedDifferenceError`, a `StatisticalUncertaintyError` subclass): unconverged
side, period mismatch, common window < 8 pairs, non-finite values, unequal lengths, bit-identical
runs (a self-comparison is not a measurement), a difference dead at **signal scale** (below
1e-12 x the underlying signal is float-cancellation noise — normalising by the diff's own scale
would never fire; by the delta mean would spuriously kill small-mean/high-variance diffs), and a
degenerate per-side batch-means estimate (period-locked alternating tail).

### 2. The schema — `aero/vv/reportable.py`

`ImprovementClaim.u95_delta: float` (free input) is **removed**, replaced by
`delta_uncertainty: DeltaU95` where `DeltaU95 = HandEnteredDeltaU95 | ComposedDeltaU95`
(discriminated on `source`, the `SolveResult.history` precedent). `u95_delta` survives as a
computed field delegating to the union (serialized key and the `SmallSignalError` validator are
unchanged — single enforcement point). `ComposedDeltaU95` RSS-composes
`sqrt(u95_numerical^2 + paired.u95_delta_statistical^2 + u95_input^2)` **as a computed field** —
there is no free total to mistype. New required `kind: QuantityKind` (no default: a defaulted
"steady" would let an unsteady delta silently skip the paired requirement — the F1 hole in new
clothing). Claim-level validators: non-steady composed requires `paired`; steady forbids it (no
per-cycle series exists); when `paired` is present the claimed `baseline`/`improved` must equal
the paired-window means (the value and its uncertainty must come from the SAME window).

`ReportableResult._thesis_grade_gate` (applied to `improvement` and to
`optimization.improvement`): thesis-grade requires **composed** source, a **positive**
paired-numerical term (matched conditions *reduce*, never zero, discretization error), and — for
non-steady kinds — a **reliable** difference-series estimate. `cancellation_effective` is
deliberately NOT gated: a weak-correlation pair with an honest wide u95 that still clears
`k * U95` is a legitimate, extra-strong claim; the diagnostic is for audit. The reliable-flag
placement is deliberately asymmetric with plain quantities (there it is composer policy, because
`ReportableQuantity` does not embed the estimator object; here the evidence IS embedded, so the
schema enforces it).

### 3. The composer — `aero/vv/reportable_compose.py::compose_improvement()`

Mirrors `compose_reportable`'s seam: `u95_delta_numerical` arrives **absolute** (GCI on the delta
/ matched-grid Richardson, caller-formed); the statistical term arrives as the typed
`PairedDeltaUncertainty`; `u95_delta_input_frac` is a fraction **of `|baseline|`** — a fraction
of the delta would shrink the bar exactly as the claim shrinks (anti-conservative, circular).
For non-steady kinds the claimed values are taken **from** the paired-window means (passing them
explicitly raises); steady claims require explicit values plus a positive numerical term.
Returns `ImprovementClaim` (claims ride in results; `compose_reportable` keeps owning result
assembly); `SmallSignalError` fires in the claim's own validator — constructing a claim IS the
claim.

## Constitution amendment (checked: the process applies only if the text changes)

No sentence of Invariant 10 becomes false — this change strengthens *how* `u95_delta` comes to
exist without altering the invariant's normative content — so the code lands without touching
`CONSTITUTION.md`. However, the Enforcement paragraph is how future sessions locate an
invariant's teeth (DOCS-MATCH-REALITY), so a **parallel micro-PR** adds one sentence to Invariant
10's Enforcement paragraph:

> `u95_delta` is *measured* by the paired-difference estimator (`aero/vv/paired_difference.py`)
> and composed by `compose_improvement()`; a hand-entered `u95_delta` cannot reach
> `thesis-grade` (ADR-023).

That PR observes the full ≥72 h amendment window (the ADR-015 proposed→accepted lifecycle) and
merges on operator approval. **Operator decision 2026-07-06:** this two-track path was chosen
explicitly (over ADR-only and over blocking the code on the window).

## Consequences

- **Positive:** Invariant 10's central number is now computed, auditable, and CI-enforced (the
  `small-signal-gate` gains `tests/vv/test_paired_difference.py` + F1-tripwire tests on a
  committed paired fixture); Stage 15 inherits a ready, validated delta-UQ path; the review's
  "treat any ImprovementClaim as provisional" caveat is closed.
- **Negative / breaking:** `ImprovementClaim`'s constructor changes (breaking; all construction
  sites were test-only — `tests/stage_10/test_reportable.py`, `tests/stage_12/
  test_small_signal_gate.py` — and were updated in the same PR; no `aero/` or `scripts/` code
  built one). The unconstructibility is **high-friction, not unforgeable**: `StatisticalUncertainty`'s
  fields are themselves free inputs, so a determined forger can fabricate an internally-consistent
  evidence object; the cross-validators raise the forging cost from "type one float" to "fabricate
  a full consistent estimator output". Stated honestly here per the review's spirit.
- **Practical bar:** at the hard floor of 8 common converged cycles, the diff's `reliable` flag is
  almost never set (`n_eff >= 8` needs `tau_int = 0.5` exactly) — plan paired campaigns around
  **~16–20 common converged cycles** or the claim stays `validated`.
- **Ledgered follow-ups:** `CycleSamples.t0` (make the same-origin alignment precondition
  machine-checkable — today it is a documented precondition, true by construction for the
  platform's paired drivers); config-hash comparison of the two runs' CaseSpecs as
  machine-checked `matched_conditions`; a real-data paired fixture with a pinned
  `variance_reduction` band when per-cycle series are next regenerated on-cluster (the committed
  fixture is seeded-synthetic — the Stage-13 artifacts contain only serialized `ReportableResult`s,
  no per-cycle series).

## Pros and cons of considered options

### Option 3 — discriminated union with embedded evidence (chosen)
- Good: the evidence itself (correlation, diff stat, per-side stats, window) must be structurally
  present; computed-field RSS kills the mistyped-total class; the union is precedented five times
  in `aero/`.
- Bad: breaking constructor change; the extra `kind` field is one more thing to state (that is
  the point).

### Option 1 — status quo + docs
- Good: zero churn. Bad: the finding, verbatim.

### Option 2 — source tag beside the float
- Good: tiny diff. Bad: a tag is as free as the float; enforcement would rest on a string.

### Option 4 — always-computed, no hand path
- Good: maximal strictness. Bad: kills legitimate exploratory claims and steady-delta workflows.

### Option 5 — analytic covariance composition
- Good: textbook-familiar. Bad: dof bookkeeping at 4–8 batches is fragile; the difference series
  measures the covariance directly with the machinery we already trust.

## Links

- Review: `docs/review/2026-07-external-review.md` (finding F1)
- Related ADRs: ADR-013 (mission), ADR-015 (Invariant 10 promotion), ADR-019 (postprocess seam),
  ADR-020 (UQ core: NOBM estimator, `compose_reportable`, the CI gates), ADR-021/022 (Stage-13
  paired laminar-vs-transition study — the first real matched-condition pair)
- Product spec: `docs/vv/output-validity-bar.md` §4; rule:
  `.claude/rules/optimization-integrity.md`
- External: ASME V&V 20-2009 §7; Roy & Oberkampf (2011) CMAME 200; common-random-numbers /
  paired-comparison variance reduction; Fishman (1978) / Schmeiser (1982); Sokal (1997)
