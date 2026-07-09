# STAGE 15 — CFD-in-the-Loop Parametric Optimization  [THESIS CHECKPOINT]

> Stage 14 delivered the validated forward problem — a rigid flapping wing whose stroke-averaged
> lift clears its Wang-Birch-Dickinson experiment anchor with a full composed U95 (overset motion,
> ADR-024). Stage 15 is **the mission**: close the loop. Run a parametric optimization *with direct
> CFD in the loop* and report a **CFD-verified improvement whose delta exceeds its combined
> uncertainty** — the platform's first thesis-grade result. Everything since Stage 01 exists to make
> this one number trustworthy.

## BEFORE YOU START — READ

1. `CLAUDE.md` (auto-loaded) — the invariants; **esp. Hard Rules 12 (IMPROVEMENT-EXCEEDS-
   UNCERTAINTY), 14 (CFD-VERIFIED-OPTIMUM-ONLY), 15 (VALIDATE-AGAINST-EXPERIMENT)** and the U95
   machinery.
2. `.aero-stage` (flip to `15` as this stage's first commit).
3. `docs/handoffs/STAGE-14-rigid-flapping-wing-DONE-*.md` — the flapping forward model, the overset
   motion path, the WBD anchor + composed U95, and the rotation-timing variants (your seeds).
4. `.claude/rules/optimization-integrity.md` (the operational form of Hard Rules 12 + 14 — read it
   in full) + `docs/vv/output-validity-bar.md` (the thesis-grade contract).
5. ADR-023 (paired-difference `u95_delta` — the delta-UQ machinery you build on) + ADR-024 (the
   flapping overset motion path). `docs/review/2026-07-external-review.md` findings **F1** (done)
   and **F3** (this stage's structure).

## Why this stage (and the F3 re-sequencing that structures it)

The external review's finding **F3** warns that Stage 15 is open-ended research scheduled
one-session — and that betting the whole loop on the (hardest, most expensive) flapping problem
first is high-risk. The mandated structure is therefore **two phases, gated**:

**Phase A — prove the loop on a cheap, already-trusted case (do this FIRST).** Stand up the
optimization loop + the delta-UQ pipeline end-to-end on physics you already trust and that is
cheap to evaluate — the **oscillating-cylinder lock-in** or the **plunging airfoil** (Stage 11/13,
minutes-to-an-hour per evaluation, matched numerics by construction). Optimize a 1–2 variable
objective (e.g. plunging Strouhal / amplitude for peak propulsive efficiency at fixed thrust).
Deliverable: a **genuinely thesis-grade delta** on trusted physics, exercising
`paired_delta_uncertainty()` → `compose_improvement()` → `ImprovementClaim` → `OptimizationResult`
before any flapping run. This buys (i) an early real result and (ii) validation of the delta-UQ
machinery independent of the 2-D flapping model's own limitations.

**Phase B — the flapping optimization (only after Phase A clears).** Optimize the Stage-14 rigid
flapping wing. The natural design variable is the **rotation-timing phase `pitch_phase_deg`**
(± the stroke amplitude `stroke_amplitude`): Stage 14's advanced / symmetrical / delayed variants
are literally the baseline/candidate seeds, evaluated at **matched mesh + numerics** by
construction (same `FlappingWingSpec`, only the motion phase differs — exactly the matched-condition
requirement for correlated-error cancellation). Objective: e.g. maximize stroke-averaged lift (or a
lift/power efficiency) — the advanced-rotation lift enhancement is the physics you are climbing.

## Deliverables

1. **The optimization loop.** A `Optimizer` over a small design space (≈2–6 vars): direct-CFD
   Bayesian optimization (recommend BoTorch/Ax or a lightweight GP + EI — pin the choice in an ADR;
   keep `aero/optimize/` core stdlib+numpy+pydantic, the BO backend behind an extra). Each proposed
   design is evaluated by **ground-truth CFD** (Hard Rule 14: no optimum on a surrogate prediction
   alone). Selection-bias-aware: the reported optimum is verified on a held-out CFD evaluation, and
   `n_candidates` is recorded (`OptimizationResult` already enforces this).
2. **The delta-UQ report.** The baseline→optimum improvement composed via
   `compose_improvement()` from the **paired-difference** estimator (`aero/vv/paired_difference.py`)
   over the common converged window, RSS with the GCI-on-the-delta and input terms. The claim is
   thesis-grade **only if** `delta > k·U95` (k=2), the SHA is clean (P1b), the diff-series estimate
   is `reliable`, and the anchor/verification holds — all enforced structurally by the schema.
   **Plan paired campaigns for ~16–20 common converged cycles per arm** — at 8 the diff estimate is
   never `reliable` and the claim caps at `validated` (ADR-023). CycleSamples share an origin/period
   for index-k pairing (documented precondition; `CycleSamples.t0` is a ledgered follow-up to make
   it machine-checkable).
3. **Constitutional promotion of Hard Rule 14** (CFD-VERIFIED-OPTIMUM-ONLY) to a CONSTITUTION
   Invariant via the ADR-015 amendment process (≥72 h window). `OptimizationResult` is the schema.
4. **ADR(s)** for the optimizer + acquisition-function choices; **post-stage handoff**; author the
   **Stage-16 prompt**; tag `v0.0.15`.

## The GO/NO-GO gate

**GO** = a `ReportableResult` carrying an `OptimizationResult` whose `ImprovementClaim` is
**thesis-grade** — a CFD-verified improvement delta that exceeds `k·U95` (k=2, matched conditions,
paired-measured `u95_delta`), on a case anchored to experiment (Phase A trusted physics; Phase B the
WBD-validated flapping model). That is the first thesis-grade result — the thesis checkpoint.

**NO-GO** = if no design clears `k·U95` (the improvement is within its own uncertainty), that is
**noise, not a result** — report the values as plain quantities, document, and do not manufacture a
claim (Invariant 10). If the loop is sound but the flapping delta is marginal, the Phase-A trusted
delta still stands as the thesis-grade demonstration. Never relax `k`, never hand-enter `u95_delta`
(`HandEnteredDeltaU95` structurally cannot reach thesis-grade).

## Carried-forward ledger (status at Stage-15 start)

- **DONE (Stage 14):** P1b (`-dirty` SHA barred from thesis-grade), P1d (`u95_input_basis` makes
  input-UQ-skipped distinguishable from ≈0). The flapping forward model + overset motion + composed
  U95 anchor.
- **OPEN (address if it bears on the claim's credibility):** **M1** — tie the batch size to the
  measured τ_int (`batch_size ≥ c·τ_int`) and tighten the estimator's known-answer tests to
  multi-seed unbiasedness; the delta-gate margin is computed against `u95_statistical`, so a biased
  error-bar weakens `delta > 2·U95`. **`CycleSamples.t0`** — machine-checkable phase alignment for
  paired/phase comparisons. **Per-phase-bin `u95_statistical`** — if a phase-resolved trace (not
  just a stroke-average) is ever gated. **P1a/P1c** — provenance hardening (dvc content fingerprint;
  verify the SIF digest at launch).

## Infra + conventions (unchanged from Stage 14)

Serial OpenFOAM in the LXC (MPI blocked); the flapping forward evaluations use the **overset** path
(`overPimpleDyMFoam`, ADR-024) via the detached long-timeout driver (`scripts/stage14_flapping_vv.py`
pattern), polling `/mnt/aero/runs`. Independent serial evaluations run concurrently on the 16-core
box (no approval); a full BO campaign of many CFD evaluations is a **cluster-cost / time gate** —
budget it and get operator sign-off before launching a large batch. Clean-tree provenance
(`allow_dirty=False`) for any thesis-grade run. Branch + PR, squash, 24 h cooling-off,
Conventional Commits `<type>(stage-15)`; the `moving` marker keeps multi-hour cases out of
`vv-required`.

## POST-STAGE HANDOFF (mandatory)

Write `docs/handoffs/STAGE-15-*-DONE-YYYY-MM-DD.md` (full frontmatter + 10 sections). Emphasize: the
Phase-A trusted-case thesis-grade delta; the optimizer + acquisition ADR; the Phase-B flapping
optimization outcome; the Hard-Rule-14 constitutional promotion. Confirm the **Stage-16 prompt
exists**. Tag `v0.0.15`.
