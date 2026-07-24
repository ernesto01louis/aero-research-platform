---
stage: 17
stage_name: "Stage 17 — Surrogate-Accelerated Optimization (own-data)"
status: complete
date_started: 2026-07-24
date_completed: 2026-07-24
session_duration_hours: 1
claude_code_version: 2.1.150
model: claude-fable-5
git_sha_start: e49e33c
git_sha_end: c5c4676d43417b99d88e029b32c2a0a959907290
stage_tag: v0.0.17
next_stage: 18
next_stage_name: "Stage 18 — Arbitrary-Geometry Ingestion + Robust Meshing"
---

# Stage 17 — Surrogate-Accelerated Optimization — DONE

## Headline

**Deliverables 1-3 GO; deliverable 4 (speed-up) an honest NO-GO by design.** The ADR-025
anti-surrogate-exploitation stack was reconciled to main (PR #33). A `gp_bootstrap` ensemble
(5 seeded bootstrap-GP members) was trained on a **42-solve own-CFD corpus** and **PROMOTED to
a `validated` certificate** — held-out ±2·std coverage 0.90 ∈ [0.85, 1.0], ld_mae p95 1.31
(≈5% of the 24.66 objective span), mean_abs_z 0.77 / std_z 1.15 (genuinely well-calibrated). It
was wired into the Stage-15 optimizer as a propose/dispose loop (`aero/optimize/accelerated.py`:
the surrogate proposes via uncertainty-routed infill inside a trust region, CFD disposes, the
incumbent updates from CFD values only). An exploratory run genuinely exercised the loop with
**16 real-CFD evals** and found **L/D 46.372 > the best of the entire 42-solve corpus (46.337)** —
a surrogate-proposed, CFD-verified improvement, 0 failures.

**The pre-registered speed-up comparison is a documented DEGENERATE NO-GO.** Direct-CFD BO
reaches the +22.2 L/D bar from scratch in **4/7/5 marginal evals** (seeds 0/1/2), mostly during
random LHS init. The training corpus already contains **5 designs past the bar** (max 46.34), so
the surrogate-accelerated loop seeds its incumbent past the bar and does **0 marginal search** in
all three seeds. The literal marginal metric would score surrogate 0 < direct as a 3/3 "win", but
that is the corpus, not the surrogate — the honest total-cost accounting (42 corpus solves vs ~5
direct) shows no single-run acceleration, so the verdict is NO-GO and the loop of record stays
direct-CFD BO (S7). **This is a real finding, not a bug:** in a cheap 2-D problem where direct BO
is already ~5-eval-efficient and a dense own-data corpus already contains the optimum, surrogate
acceleration has no single-run headroom — its payoff is in higher-dimensional / more expensive
regimes and amortized across many runs. The reported optimum is the surrogate-found design
(L/D 46.372, m≈0.0714 p≈0.2198), held-out CFD-verified, tier **capped at `validated`** (Stage-16's
3-grid analysis found sub-first-order convergence, order 0.465 < 0.5, so a 2-grid fallback GCI
cannot upgrade the tier — thesis-grade rests on the ledgered 393² rung).

## 1. Deliverables status
- ✅ **Own-data surrogate + validated cert** — gp_bootstrap ensemble, PROMOTED validated
  (`data/vv/stage17_surrogate_cert.json`); C1-C4 pass, calibrated.
- ✅ **Surrogate-in-the-loop via the ADR-025 stack** — `aero/optimize/accelerated.py`; demonstrated
  end-to-end with 16 real-CFD evals (`data/vv/stage17_arm_surrogate_explore.json`), trust-region +
  uncertainty-routed infill + retrain, 0 failures.
- ✅ **Every optimum CFD-verified (Invariant 12)** — reported optimum is a held-out CFD re-solve,
  `surrogate_predicted=True`, `n_candidates=74`, `held_out_verification=True`
  (`data/vv/stage17_optimization.json`).
- ⚠️ **Honest speed-up demo** — NO-GO (degenerate): corpus already past the bar; documented in
  `data/vv/stage17_speedup.json` with both accountings. Fall back to direct-CFD BO.

## 2. Decisions made (rationale)
- **Reconciliation (ADR-031):** merged `feat/stage-14-anti-surrogate-exploitation` with 5
  pre-determined resolutions; dropped the DRAFT prompt with a clause disposition table; **calibration
  band amended [0.85, 0.99] → [0.85, 1.0]** pre-campaign (at n≈10 holdout a perfectly calibrated
  estimator hits coverage 1.0 with p≈0.62; DRAFT's own "ratify or amend"); **GO-bar registered
  reading** (race to a CFD-verified delta bar at the campaign grid at the validated tier, not
  literal thesis-grade — bounded by the Stage-16 verdict).
- **Member family = seeded bootstrap GP** (`gp_bootstrap`), not torch-MLP: torch absent on the host
  and MLPs calibrate poorly on ~40 points (would flunk C1).
- **Pre-registration (ADR-032):** the full gate block (C1-C4, L1-L5, S1-S8, V1-V3) was committed
  before any campaign solve. It was NEVER relaxed — the degenerate NO-GO, the corpus_v2 cert
  refusal, and the tier cap are all the gates holding.
- **Tier cap thesis-grade → validated:** a 2-grid fallback GCI cannot upgrade the tier above
  Stage-16's 3-grid sub-first-order finding.

## 3. Deviations from the plan
- Both adversarial-review workflows: the first was killed by a session usage limit (review done
  inline; 1 edge-case fix); the final one ran at close-out.
- The plan expected the speed-up comparison to be run "as designed"; it turned out DEGENERATE
  (corpus contains past-bar designs). Handled by honest NO-GO + an exploratory loop that genuinely
  exercises the machinery (deliverable-2 evidence the pre-registered arms could not provide).
- corpus_v2 cert re-issue REFUSED (p95 2.62 > 2.5): naive exploit-heavy flywheel growth degraded
  calibration. Gate honored; base-42 validated cert stays the cert of record.

## 4. Env / schema changes
- Additive (all defaults preserved): `gp_bootstrap` basis Literal in `SurrogatePrediction`,
  `UncertaintyCalibration`, `compute_uncertainty_calibration`; `EnsembleSurrogate` gained
  `basis=`/`metric_name=` + fail-loud `promote_to_validated` (`PromotionRefused`).
- New modules: `aero/surrogates/gp_bootstrap.py`, `aero/optimize/{corpus,accelerated,speedup}.py`.
- New DVC dataset `data/datasets/stage17_naca4_ld/` (corpus.json 42 rows + corpus_v2.json 16 rows).
- `stage_17` pytest marker; `.aero-stage` → 17.

## 5. CI/CD changes
- Pinned dev `ruff` to 0.15.13 (pre-commit rev): an unpinned drift reformatted a markdown doc and
  broke the required lint check on a PR touching no markdown.

## 6. Gotchas discovered
- **`dataset_hash` needs the tracked FILE path, not the dataset dir** (`dvc status -c <dir>` errors;
  datasets track individual files so reference.md/LICENSE stay in git).
- **The speed-up-to-a-bar metric is degenerate when the own-data corpus already contains past-bar
  designs** — the surrogate does 0 marginal search. The fair test needs a reduced prior (ledgered).
- **Naive exploit-heavy flywheel growth degrades calibration** (corpus_v2 cert refusal) — the
  explore route matters for keeping the corpus balanced.
- **A 2-grid fallback GCI can spuriously reach thesis-grade** on a large delta; the tier must be
  capped by the more rigorous 3-grid finding.
- **Single self-hosted vv runner:** non-required vv-smoke starves the required V&V checks.
- Clean-tree discipline: write solve bundles to scratchpad, commit between phases — an untracked
  close-out doc mid-campaign dirties the tree and fails clean-tree provenance.

## 7. Open items for the next stage (and beyond)
- STAGE-18 prompt exists (`docs/handoff-bundle/STAGE-18-arbitrary-geometry-ingestion.md`).
- **Ledger:** the fair-test (reduced-prior / higher-DV) surrogate-speed-up experiment; balanced
  flywheel-growth / corpus curation (explore/exploit ratio for corpus_v2); content-addressed
  dataset hash (the sync-state hash is coarse); direct-arm evals into the corpus (EvalRow lacks the
  four-tuple); 393² certification rung (still open from Stage 16); anisotropic trust-region radii;
  std recalibration. MLflow campaign logging is now ON (Stage-15 ledger item closed).

## 8. Pointers for next session
- Read first: this handoff → ADR-031 → ADR-032 → `data/vv/stage17_speedup.json`. Do NOT re-read the
  Stage-16 certification detail unless revisiting the 393² rung.
- Verify: `data/vv/stage17_optimization.json` (validated, surrogate-found, CFD-verified);
  `stage17_surrogate_cert.json` (validated); the 7 arm bundles.

## 9. Artifacts produced
- Corpus (42 solves) + corpus_v2 (16); validated cert + v2-refused record; 3 direct + 3 surrogate +
  1 exploratory arm bundles; speed-up verdict + CFD-verified reported optimum. ADR-031, ADR-032,
  STAGE-18 prompt. New modules + 36 stage-17 tests. Full suite green (645+), mypy strict, ruff clean.

## 10. Confidence / risk
- **High confidence:** the surrogate is genuinely validated and well-calibrated; the loop works with
  real CFD (16-eval demonstration); every reported optimum is CFD-verified; the honest NO-GO is
  correctly derived and the gates were never relaxed.
- **Honest limitation:** the pre-registered speed-up experiment did not discriminate (degenerate).
  The claim that surrogate acceleration CAN help is NOT established here — only that it is not needed
  in this cheap 2-D regime. The fair test is future work.
- **Read the tier honestly:** `stage17_optimization.json` carries an `OptimizationResult` (the
  Invariant-12 canonical record for a surrogate-found optimum) whose embedded `ImprovementClaim`
  reports a 2-grid matched-grid `u95_delta` ≈ 2.08. That 2-grid GCI assumes near-first-order
  convergence; Stage-16's 3-grid analysis measured observed order 0.465, at which the true delta
  uncertainty is far larger and the +24.7 delta does NOT clear thesis-grade significance. The
  `validated` tag is the operative honest statement: the delta is real and robustly positive at
  every grid, but its grid-convergence uncertainty is not certified. Do not read the embedded
  2-grid significance as a thesis-grade claim — thesis-grade rests on the ledgered 393² rung.
- **Bus factor:** every claim number is in a committed JSON with run_ids + clean four-fold
  provenance; raw force series on /mnt/aero/runs (aero-dev) may be reclaimed.
