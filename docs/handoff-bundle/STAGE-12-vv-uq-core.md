# STAGE 12 — Verification & UQ Core (the `u95` machinery)

> The optimizer's integrity layer. Stage 11 gave the platform *unsteady numbers from a
> cycle-converged limit cycle*; Stage 12 puts an **error bar** on them — the `U95` envelope
> that makes a reported effect (and, at Stage 15, an optimization delta) thesis-grade. This
> is the stage that turns `aero/vv/reportable.py` from a schema skeleton into a live gate.

## BEFORE YOU START — READ

1. `CLAUDE.md` (auto-loaded) — esp. Hard Rules 12 (IMPROVEMENT-EXCEEDS-UNCERTAINTY) + 13
   (NO-SURROGATE-ON-FOREIGN-DATA), and the production-tag UQ block.
2. `.aero-stage` (flip to `12` as this stage's first commit).
3. `docs/handoffs/STAGE-11-moving-mesh-and-unsteady-DONE-*.md` — what Stage 11 delivered (the
   moving-mesh path, the `aero/postprocess/` toolkit, the two moving-body GO/CONCERN results)
   and, crucially, **the seam it exposed for you**: `aero.postprocess.phase_averaging`
   (`segment_cycles` → `CycleSamples.per_cycle_mean`) + `cycle_detection` (the converged tail).
4. ADR-015 (Invariants 10 + 11), ADR-013 (mission), ADR-019 (postprocess API);
   `docs/vv/output-validity-bar.md` (the product spec you are implementing).
5. `.claude/rules/optimization-integrity.md` + `flapping-validation-ladder.md`.
6. Read first: `aero/vv/reportable.py` (the `ReportableResult` / `ReportableQuantity` /
   `ImprovementClaim` schema + the `_thesis_grade_gate`), `aero/vv/mesh_sweep.py` (the GCI /
   `u95_numerical` machinery already built), `aero/postprocess/{phase_averaging,cycle_detection}.py`.
   Run to verify the world: `pytest tests/stage_11 tests/unit -q`, `mypy aero`, `ruff check aero tests`.

## Why this stage

`reportable.py` already **defines** the contract: a non-steady thesis-grade quantity needs
`u95_statistical > 0`, and an `ImprovementClaim` must clear `k·U95`. But nothing **computes**
`u95_statistical` yet, and the CI gate that enforces the small-signal rule does not exist.
Stage 11 deliberately exposed the per-cycle samples (`CycleSamples.per_cycle_mean` over the
converged tail) so Stage 12 can turn them into a statistical uncertainty. Without this, no
unsteady flapping result — and no optimization delta (Stage 15) — can be tagged thesis-grade.

## Deliverables

1. **`u95_statistical` compute.** A batch-means / autocorrelation **effective-sample-size**
   estimator over the converged limit cycle: consume `CycleSamples.per_cycle_mean[
   converged_from_cycle:]` (the Stage-11 seam) → the standard error of the time/phase-average
   → the 95 % half-width. Live in `aero/vv/` (strict-pydantic, stdlib+numpy). Validate on the
   Stage-11 oscillating-cylinder + plunging-foil runs (the cylinder St and the foil C_T get a
   real `u95_statistical`). Handle the small-N cycle count honestly (t-quantile, not 1.96).
2. **Full `U95` composition end-to-end.** Wire `u95_numerical` (the existing GCI mesh-sweep;
   run the deferred moving-case GCI here — a combined space+time study for at least the
   cylinder), `u95_statistical` (new), and `u95_input` (parametric / digitization — e.g. the
   Heathcote-Gursul digitization uncertainty flagged in Stage 11) into a live
   `ReportableResult` for an unsteady case, RSS-combined.
3. **Invariant-10 CI gate — `small-signal-gate`.** A CI job that fails a build if a
   thesis-grade non-steady quantity has `u95_statistical == 0`, or if an `ImprovementClaim`'s
   delta does not exceed `k·U95`. Make it a **required** status check.
4. **Invariant-11 `data_origin` fence.** Add the `data_origin` field + the CI fence that a
   `validated`/`production` surrogate certificate cannot be issued on foreign
   (automotive/aircraft) data (reuses the Stage-08 taint machinery). Merge the ADR-015
   constitution PR (post-72 h window) promoting Invariants 10 + 11.
5. **Rigor follow-ups from Stage 11** (fold in here): clean-SHA reportable re-runs of the
   moving-body cases (Stage-11 GOs used `--allow-dirty`); **verify the Heathcote-Gursul
   digitized C_T points against the primary figure** (Stage-11 flagged this — the foil
   reference `u95_input` depends on it); a GCI sweep per moving case.
6. ADR for the UQ-core decisions (the batch-means estimator + N_eff method; the CI gates).
   Post-stage handoff + author the Stage-13 prompt (`docs/handoff-bundle/STAGE-13-transition-and-unsteady-airfoil.md`). Tag `v0.0.12`.

## The GO/NO-GO gate

**GO** = an unsteady case (the Stage-11 cylinder and/or foil) carries a full, RSS-composed
`U95` — with a **non-zero, defensible `u95_statistical`** from batch-means over the converged
cycles — end-to-end into a `ReportableResult`; the `small-signal-gate` + `data_origin` CI
jobs are green and required; the ADR-015 constitution PR is merged.

**NO-GO** = if the batch-means estimator cannot produce a stable `u95_statistical` (e.g. the
limit cycle is not actually converged, or N_eff is too small), STOP — the Stage-11 unsteady
path is not trustworthy enough to gate optimization deltas on. Investigate the
cycle-convergence, not the estimator, before proceeding.

*Scope note:* the optimization loop itself is **Stage 15**; Stage 12 builds the *gate* the
loop will pass through, exercised here on a single unsteady quantity (not an optimization
delta). Transition (`kOmegaSSTLM`) is **Stage 13**.

## POST-STAGE HANDOFF (mandatory)

Write `docs/handoffs/STAGE-12-vv-uq-core-DONE-YYYY-MM-DD.md` (full frontmatter + 10 sections,
`.claude/rules/handoff-discipline.md`). Emphasize: the batch-means estimator + N_eff method
(with the MLflow runs showing the composed U95); the two new required CI gates; the
constitution-promotion merge. Confirm the **Stage-13 prompt exists**. Then tag `v0.0.12`.
