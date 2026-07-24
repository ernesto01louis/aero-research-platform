# ADR-032 — Surrogate-accelerated loop design and the pre-registered speed-up protocol

- **Status:** accepted
- **Date:** 2026-07-24
- **Deciders:** Operator (Louis Ernesto Schulte Moredo, via approved Stage-17 plan); Claude Code
  agent (Stage 17)
- **Stage:** 17

## Context and problem statement

Stage 17 must wire the ADR-025 stack into the Stage-15 optimizer so the surrogate
proposes and CFD disposes, and demonstrate the speed-up honestly against direct-CFD BO.
The comparison is only worth anything if its bar, budget, and decision rule are committed
BEFORE any campaign solve — Stages 15-16 retracted or blocked three post-hoc shortcuts,
and the platform's value is that the gates never move after data exists. This ADR fixes
the loop design, the corpus/certificate mechanics, and the full pre-registered gate
block. The gate block is duplicated verbatim in `scripts/stage17_speedup_arm.py`'s
docstring (the operational copy of record); any drift between the two is a bug.

## Decision outcome

### Loop design (`aero/optimize/accelerated.py`)

`SurrogateAcceleratedOptimizer` per iteration: (1) retrain fresh
`GPBootstrapMember`s into an `EnsembleSurrogate` on corpus + accumulated infill rows and
re-issue a smoke-tier operational certificate; (2) Invariant-9 gate — `assert_current`
against a freshly recomputed dataset hash, once per iteration, before any prediction is
consumed; (3) propose a seeded uniform pool inside `TrustRegionPolicy.bounds`, ranked by
`rank_infill_candidates` (top-EI exploit + reserved explore fraction); (4) dispose —
every selected candidate goes to ground-truth CFD; the incumbent updates from CFD values
ONLY (Invariant 12 by construction); (5) trust-region ratio test fed only the top
exploit candidate and only when its prediction strictly improves the pre-batch incumbent
(the ADR-025 `TrustRegionError` doctrine); reject-floor re-opens the region on the
incumbent; an explore-candidate win re-centers the box with radius/counters preserved
(`trust_recentered` recorded); (6) stop on target/budget/distrust. Every iteration
serializes to a frozen `IterationRecord` (certificate, routed candidates, aligned
results incl. failures, trust trail) — the campaign bundle is auditable and replayable.

The direct-CFD `BayesianOptimizer` is byte-untouched: it is the control arm.

### Certificate lifecycle and the dataset-hash finding

`dataset_hash()` is a DVC **sync-state** fingerprint (sha256 over
`dvc status -c --json <path>`; the empty-status digest is the intended in-sync value) —
NOT a content hash. Consequences, recorded honestly: the Invariant-9 data gate catches
on-disk corpus drift and expiry, but mid-campaign in-memory infill rows are invisible to
it, so the retrain-and-re-certify cadence (gate L4) is loop-enforced rather than
gate-forced; and the **cert of record** must be issued on the COMMITTED final corpus
(base + infill rows, `corpus_v2.json`, DVC-added and pushed) — mid-campaign certs are
operational only. A content-addressed dataset hash is ledgered as follow-up. Mid-campaign
retrain certs label their dataset honestly (`stage17-naca4-ld+infill<N>`).

### Own-data corpus (`aero/optimize/corpus.py`, Invariant 11)

The Stage-15 BO evaluations were never persisted (`--no-mlflow`), so the training corpus
is generated fresh: seeded LHS (n=40, seed=170) over the Stage-15 design space at the
campaign grid, plus the m=0 baseline and Stage-15-optimum anchors — every row a
ground-truth solve with four-fold clean-tree provenance, failures recorded as evidence.
Samples assert `data_origin="platform-validated"` explicitly. The corpus builder lives in
`aero/optimize/` because the `data-origin-fence` treats everything under
`aero/surrogates/_common/loaders/` as foreign corpus loaders. Storage:
`data/datasets/stage17_naca4_ld/` (DVC-tracked; the Invariant-9 data-gate path). MLflow
campaign logging is ON (server + Postgres mirror verified reachable) — closing the
Stage-15 ledger item; the committed JSON bundles remain the evidence of record.

## The pre-registered gate block (committed before any campaign solve; NEVER relaxed)

Certification (smoke → validated), seeded 25% held-out split of the training corpus:

- **C1** empirical ±2·std coverage ∈ [0.85, 1.0] (band amendment rationale: ADR-031).
- **C2** held-out |L/D error| p95 ≤ 2.5 (~10% of the corpus objective span).
- **C3** non-collapsed ensemble (structural: `CalibrationError` aborts the build).
- **C4** every sample `data_origin == "platform-validated"` (Invariant 11).
- **D1** `mean_abs_z` / `std_z` / coverage reported as diagnostics, never gated.

Loop configuration (frozen): **L1** `TrustRegionConfig` defaults (initial 0.25 /
min 1e-3 / max 0.5, expand 2.0, shrink 0.5, η_accept 0.25 / η_expand 0.75), unit cube;
**L2** infill batch 4 (3 exploit + 1 explore, explore_fraction 0.25); **L3** candidate
pool 2048 inside the trust region; **L4** retrain + re-issue cert every iteration,
`assert_current` once per iteration; **L5** stop at bar | 16 ground-truth evals |
2 consecutive reject-floor events without incumbent improvement (→ NO-GO fallback).
Member family: 5 × GP(matérn-5/2), length scales {0.20, 0.25, 0.30, 0.35, 0.40};
ensemble fit seed 17, calibration_fraction 0.25, interval_k 2.0.

Speed-up comparison (paired seeds):

- **S1** seeds {0, 1, 2}; both arms share the design space (m ∈ [0, 0.08],
  p ∈ [0.2, 0.6]), base-grid `ShapedTurbulentAirfoil` (k-ω SST, Re 5e5, AoA 4°,
  end_time 3000), metric L/D.
- **S2** direct arm = Stage-15 configuration verbatim (n_init 6, n_iter 10, xi 0.01,
  pool 2048) on the untouched `BayesianOptimizer`.
- **S3** bar Δ* = +22.20 L/D over the m=0 baseline at the campaign grid (90% of the
  Stage-15 recorded base-grid delta 24.66, rounded to 0.01; the baseline reference value
  is the corpus baseline-anchor solve `s17c_base`).
- **S4** figure of merit = MARGINAL ground-truth evals to the first CFD-verified value at
  or past the bar; the TOTAL-including-corpus accounting is ALWAYS reported alongside.
- **S5** an arm not reaching Δ* within 16 evals is censored; a seed where neither arm
  reaches it counts AGAINST GO.
- **S6** GO ⇔ surrogate arm strictly fewer marginal evals in ≥ 2 of 3 seeds AND the cert
  of record is valid (C1-C4, in-window, data gate) AND the optimum passes V1-V3.
- **S7** NO-GO fallback: direct-CFD BO remains the loop of record; document.
- **S8** failed solves count as spent evals in both arms; within a surrogate batch the
  eval order is the deterministic infill rank order.

Final-optimum verification (Invariant 12; the claim TIER is bounded by the Stage-16
verdict — the GO-bar reading is ADR-031's registered amendment):

- **V1** held-out fresh CFD re-solve of the reported optimum → `cfd_verified` four-tuple;
  `n_candidates` = corpus + every marginal eval of the selected family;
  `held_out_verification=True`.
- **V2** matched-grid pair (base + 1.7× coarse) vs the m=0 baseline via
  `compose_result`, k = 2; if significance fails, the tag stays `validated` and is
  reported so.
- **V3** `surrogate_predicted=True` on the `OptimizationResult` (False on the S7
  fallback family).

Contingency (pre-registered): the corpus may be EXTENDED by further seeded LHS batches
BEFORE any speed-up arm runs if C1/C2 fail on first training. The gates never move.

### Consequences

- **Positive:** the comparison is decided by rules older than its data; every optimum is
  structurally CFD-verified; the campaign is fully replayable from frozen evidence.
- **Negative:** the independent-seeds comparison at n=3 is a small sample — the 2-of-3
  rule is a coarse decision boundary, honestly labelled (a larger replicate study is
  future work); the sync-state data gate is weaker than content addressing (ledgered).
- **Neutral / followup:** content-addressed dataset hash; direct-arm evals joining the
  corpus (EvalRow lacks the four-fold tuple today); anisotropic trust-region radii and
  std recalibration remain ledgered from ADR-025.
