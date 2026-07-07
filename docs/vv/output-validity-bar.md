# The output-validity bar — what "thesis-grade" means, operationally

> The platform's *product* is a trustworthy result. This document is the operational
> definition of the bar a result must clear to be tagged **`thesis-grade`**. It is the
> product spec for CONSTITUTION Invariant 10 (and Hard Rules 12, 14, 15, 16). The bar is
> **enforced in code** by `aero/vv/reportable.py` (`ReportableResult`); this document is the
> human-readable contract behind that schema.
>
> Status: the schema + this definition land in **Stage 10**. The full `u95_statistical`
> *computation* (batch-means tooling) and the required `small-signal-gate` CI job land in
> **Stage 12** (ADR-015). `ImprovementClaim`/`OptimizationResult` are exercised in **Stage 15**.

A result is **thesis-grade** iff all five hold. A `ReportableResult` with
`validation_tag="thesis-grade"` is constructible only when its validators confirm them;
`smoke` and `validated` tags carry no such gate.

## 1. Complete provenance (the four-tuple)

Every reported quantity carries a `ProvenanceTuple` — `(git_sha, dvc_input_hash,
container_sif_sha256, config_hash)`. A number without its four-tuple is not reportable
(CONSTITUTION Invariant 3). This is what lets a third party identify exactly the code,
data, container, and config that produced it.

## 2. Validation against experiment / DNS

The result is anchored to **measured or DNS reference data** via a passing
`ValidationAnchor` (reference, citation, tolerance, observed error ≤ tolerance) — not
against another CFD run or a workshop-consensus band alone (Hard Rule 15;
`.claude/rules/flapping-validation-ladder.md`). A CFD-verified `OptimizationResult` may
substitute for an anchor (see §5); the forward model it relies on is itself anchored
upstream by stage sequencing (Stage 14 validates before Stage 15 optimizes).

## 3. Quantified uncertainty — U95 = RSS of three independent contributions

```
U95 = sqrt( u95_numerical**2 + u95_statistical**2 + u95_input**2 )
```

- `u95_numerical` — discretization uncertainty. ASME V&V 20 / Roache GCI from a grid
  triplet in the asymptotic range (`aero/vv/mesh_sweep.py`). **Required > 0** for every
  thesis-grade quantity. GCI covers *only* this term.
- `u95_statistical` — the sampling error of a **time- or phase-averaged** quantity
  (batch-means / autocorrelation effective-sample-size, after a periodic-steady-state
  cycle-convergence check). **Required > 0** for any quantity whose `kind` is
  `time_averaged` or `phase_averaged` — GCI alone is insufficient for unsteady flows.
  (Steady quantities may set it to 0.)
- `u95_input` — parametric (input) uncertainty; 0 if no input-UQ was performed.

## 4. The small-signal rule — improvement must exceed uncertainty

No reported effect or claimed improvement is thesis-grade unless its CFD-verified delta
exceeds `k · U95` (margin `k ≥ 1`, default **k = 2**) — the IMPROVEMENT-EXCEEDS-UNCERTAINTY
invariant (Hard Rule 12). For an optimization **delta**, the baseline and the candidate are
evaluated at **matched numerics / mesh-topology** so correlated errors cancel. A delta within
its own uncertainty is numerical noise, not a result.

Since the 2026-07 review (finding F1; ADR-023) the delta's U95 is **measured, not asserted**:

- the **paired-difference estimator** (`aero/vv/paired_difference.py`) runs the existing
  NOBM + τ_int machinery on the per-cycle **difference series** over the common converged
  window — the diff's half-width *is* the post-cancellation statistical term;
- the empirical baseline↔candidate **correlation** and the **`variance_reduction`** ratio
  against the independent RSS are recorded in the claim, so the cancellation is auditable —
  a weakly/anti-correlated pair surfaces as `variance_reduction ≥ 1`, never hides;
- `u95_delta = RSS(paired numerical [GCI on the delta], paired statistical, input)` is a
  **computed field** of `ComposedDeltaU95` (`compose_improvement()` assembles it);
- a hand-entered `u95_delta` (`HandEnteredDeltaU95`) stays constructible for exploratory
  tiers but **structurally cannot reach thesis-grade**; thesis grade additionally requires a
  positive paired-numerical term and a `reliable` difference-series estimate.

## 5. CFD-verified optima only, and reproducibility

- **CFD-verified-optimum-only** (Hard Rule 14): every reported optimum is verified by a
  ground-truth-CFD run (`OptimizationResult.cfd_verified` four-tuple) — never reported on a
  surrogate prediction alone. Best-of-N reporting records the pool size and requires
  held-out verification (selection-bias guard; Luo et al. arXiv:2509.08713).
- **Results must travel** (Hard Rule 16): the result exports as a self-describing bundle
  (CaseSpec + four-tuple + U95 + validity context) so a third party can re-run and land
  within the stated bounds. Full bundle + round-trip CI land in Stage 20.

## Enforcement map

| Bar | Enforced by | Lands |
|---|---|---|
| Four-tuple present | `ReportableResult.provenance: ProvenanceTuple` | Stage 10 (schema) |
| Experiment anchor | `_thesis_grade_gate` requires a passing `ValidationAnchor` or CFD-verified optimization | Stage 10 |
| `u95_numerical > 0` (all) + `u95_statistical > 0` (non-steady) | `_thesis_grade_gate` | Stage 10 (gate); batch-means compute Stage 12 |
| `delta > k·U95`, matched-condition | `ImprovementClaim` validator (`SmallSignalError`) | Stage 10 (schema); `small-signal-gate` CI Stage 12 |
| `u95_delta` computed, never trusted (cancellation measured) | `DeltaU95` union + `paired_difference.py` + thesis-grade gate | Stage 13 (review F1; ADR-023) |
| CFD-verified optimum + selection-bias guard | `OptimizationResult` validators | Stage 10 (schema); exercised Stage 15 |
