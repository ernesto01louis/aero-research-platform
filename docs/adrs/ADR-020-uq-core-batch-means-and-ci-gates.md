# ADR-020 — UQ core: batch-means `u95_statistical`, full-U95 composition, and the Invariant 10/11 CI gates

- **Status:** accepted
- **Date:** 2026-07-05
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 12)
- **Stage:** 12
- **Supersedes:** none

## Context and problem statement

Stage 11 exposed cycle-converged per-cycle samples (`CycleSamples.per_cycle_mean` over the
settled tail). `aero/vv/reportable.py` *defines* the thesis-grade contract — a non-steady
quantity needs `u95_statistical > 0`, an `ImprovementClaim` must clear `k·U95` — but nothing
*computed* `u95_statistical`, and the CI gates enforcing CONSTITUTION Invariants 10 (IMPROVEMENT-
EXCEEDS-UNCERTAINTY) + 11 (NO-SURROGATE-ON-FOREIGN-DATA) did not exist. Stage 12 turns the
schema skeleton into a live, CI-enforced gate and demonstrates the full `U95 = RSS(u95_numerical,
u95_statistical, u95_input)` end-to-end on an unsteady case.

## Decision drivers

- **PLATFORM-NOT-HUB.** The estimator + composer live in `aero/` core → stdlib + numpy + pydantic
  only (no scipy).
- **Honest small-N UQ.** The converged tail is O(20–35) cycle means and cycle-to-cycle
  correlated; a naive `σ/√N` under-states the error.
- **Fail-loud / fail-closed.** A non-trustworthy statistical term or a foreign-data cert must be
  refused, not silently downgraded.
- **Required-safe CI.** Both new gates must be promotable to required status checks without a
  self-hosted-runner dependency.

## Considered options + decision outcome

### 1. `u95_statistical` estimator — `aero/vv/statistical_uncertainty.py`

**Chosen:** non-overlapping batch means (NOBM) as the **primary** estimator, with the
Sokal-windowed **integrated autocorrelation time → N_eff** as an independent **cross-check**.

- **Batch rule:** `n_batches = min(max(4, floor(√N)), 8)`; remainder dropped from the *front*
  (transient-adjacent). Student-t half-width at `n_batches − 1` df via a **committed t-table**
  (df ∈ [3,7] is the only reachable range → exact, scipy-free). At N=35 → df=4 (t≈2.776); at N=19
  → df=3 (t≈3.18) — honestly fat, which is *why* the foil stays a CONCERN.
- **Hard NO-GO (raise `StatisticalUncertaintyError`):** the tail is not converged; `N < 8`; a
  **relative** dead-signal guard (`std ≤ 1e-12·scale` — an all-equal tail has std ~1e-16 in
  float64, so a bare `== 0` misses it).
- **Soft `reliable` flag (not a raise):** the NOBM/τ_int ratio must be in [0.5, 2.0] **and**
  `N_eff ≥ 8`. Rationale (empirically established): with a handful of batches `s_batch` is itself
  noisy, and the Sokal window structurally bounds `N_eff ≳ 4.8` for correlated data — so a hard
  N_eff floor is unreachable/twitchy. The estimator returns an honest (wide) number; the
  **composer** is where an unreliable term is refused a publication tag. This is the computable
  form of the Stage-12 GO/NO-GO "is the estimate stable?".
- **Rejected:** τ_int/N_eff as the *primary* (biased-low on short series → over-states N_eff); a
  hard `crosscheck-ratio` raise (spuriously NO-GO'd a plausible converged limit cycle in testing);
  1.96 instead of Student-t (dishonest at small N).
- **Validated:** IID recovers `1.96·σ/√N`; injected AR(1) drops N_eff by the analytic factor; and
  on the **real cylinder** tail (35 converged cycles) → `u95_statistical(Cd)=0.0131`, reliable,
  `N_eff=8.5` (τ=2.05 — the estimator correctly catches the drag's real autocorrelation).

References: ASME V&V 20-2009 §7; Roy & Oberkampf (2011) CMAME 200; Fishman (1978) / Schmeiser
(1982) batch means; Sokal (1997) automatic windowing.

### 2. Full-U95 composition — `aero/vv/reportable_compose.py`

**Chosen:** a pure `compose_reportable(...)` that RSS-composes `u95_numerical` (GCI fraction ×
|value|) + `u95_statistical` (batch-means) + `u95_input` (fraction × |value|) into a
`ReportableResult`, with a **conservative tag policy**: `thesis-grade` is issued only with a
positive numerical U95, a positive **and reliable** statistical U95 (non-steady), and a **passing
anchor** — anything short downgrades to `validated`. This is where an unreliable estimate or a
failing validation (the over-predicting foil) is kept out of a publication tag **without relaxing
a tolerance**. The `scripts/stage12_reportable.py` driver produces + MLflow-logs a moving case's
result from a run dir + the GCI JSON.

### 3. Combined space+time GCI (`u95_numerical`) — `scripts/stage12_cylinder_gci.py`

**Chosen:** `u95_numerical = RSS(gci_space, gci_time)` — two **separate 1-D studies** (Celik/ASME
V&V 20 GCI is single-parameter Richardson): a **3-grid spatial GCI** (`MeshSweep`, refinement
1.0/1.3/1.7, on cycle-mean Cd — a smooth Richardson target, vs the frequency-quantized Strouhal)
and a **2-grid temporal bound** (`refined_dt` scaling the Courant-driven `max_courant`, since
`refined()` cannot touch the timestep). Each moving solve is ~30–84 min serial (**MPI blocked in
the LXC**), so the study runs via a detached driver, not `aero vv run`.

### 4. Invariant-10 gate — `.github/workflows/small-signal-gate.yml`

Pure-pytest on **ubuntu-latest** (the schema + estimator are numpy/pydantic — no cluster), so it
is required-safe. Asserts a thesis-grade non-steady quantity with `u95_statistical == 0` is
rejected, an `ImprovementClaim` within `k·U95` fails loud, and the estimator yields `u95>0` on a
committed converged-cycle fixture.

### 5. Invariant-11 fence — `.github/workflows/data-origin-fence.yml`

`data_origin: Literal["platform-validated","foreign"]` on the `Sample`/cert (default **`foreign`**
= fail-closed), a write-once taint on `Surrogate`, and a **schema validator making a foreign +
validated/production cert unconstructible on every path**. The fence (grep + runtime test on
ubuntu-latest) asserts every loader tags `foreign`. Consequence: DoMINO-on-DrivAerML (foreign) can
no longer be `validated` — the existing Cd-gate/compare tests were re-pointed at synthetic
platform-validated data.

## Consequences

- **Positive:** the optimizer's central UQ guarantee is now computed + CI-enforced; the two
  gates are required-safe (ubuntu-latest); the foil CONCERN is handled honestly (validated, not
  thesis-grade) with no tolerance relaxed.
- **Negative:** the space+time GCI is expensive serial cluster compute (~3.3 h/cylinder); the
  temporal arm is a 2-grid *bound*, not a full Richardson study (documented).
- **Neutral / followup:** foil root-cause (2-D-laminar over-prediction; low-St re-anchor) →
  Stage 13; a full 3-grid temporal GCI and a foil GCI are deferred (foil is a CONCERN regardless).

## Links

- Related: ADR-013 (mission), ADR-015 (Invariants 10+11), ADR-017 (Stage-10 transient seed),
  ADR-019 (postprocess API / the batch-means seam).
- Schema: `aero/vv/reportable.py`; product spec: `docs/vv/output-validity-bar.md`.
- Rules: `.claude/rules/{optimization-integrity,flapping-validation-ladder}.md`.
