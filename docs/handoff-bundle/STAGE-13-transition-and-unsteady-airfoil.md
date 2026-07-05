# STAGE 13 — Transition + Unsteady-Airfoil Validation

> Stage 12 gave every reported number an **error bar** (`U95`). Stage 13 makes the platform's
> *physics* trustworthy in the low-Re transitional regime the flapping flagship lives in: a
> transition model (`kOmegaSSTLM`, γ-Reθ) and experiment-anchored **pitching/plunging airfoil**
> validation (McCroskey dynamic stall; Heathcote-Gursul). It also **resolves the Stage-11/12
> plunging-foil over-prediction** — the case's proper ladder home.

## BEFORE YOU START — READ

1. `CLAUDE.md` (auto-loaded) — invariants; esp. Hard Rule 15 (VALIDATE-AGAINST-EXPERIMENT) +
   the four-fold provenance + the U95 machinery (Stage 12 shipped it).
2. `.aero-stage` (flip to `13` as this stage's first commit).
3. `docs/handoffs/STAGE-12-vv-uq-core-DONE-*.md` — the U95 core: `aero/vv/statistical_uncertainty.py`
   (batch-means `u95_statistical`), `aero/vv/reportable_compose.py` + `scripts/stage12_reportable.py`
   (compose + MLflow-log a full-U95 `ReportableResult`), `scripts/stage12_cylinder_gci.py` (the
   space+time GCI pattern). **Reuse this machinery for every Stage-13 validated result.**
4. `.claude/rules/flapping-validation-ladder.md` (Stage-13 rung: pitching/plunging airfoil vs
   McCroskey / Heathcote-Gursul) + `optimization-integrity.md`.
5. `data/references/unsteady/plunging_airfoil_hg2007/reference.md` — **the corrected primary-source
   HG reference** (C_T ≈ 0.20–0.22 over St 0.2–0.3; our 2-D laminar solve over-predicts ~2–4×).
6. ADR-017 (Stage-10 transient seed + base-drag budget) for the NACA-0012 transient-mean debt.

## Why this stage

The flapping regime (Re 10²–10⁴) is **transitional** — fully-laminar and fully-turbulent RANS
both mispredict it. Stage 12's foil result exposed this concretely: a 2-D **laminar** plunging
NACA-0012 over-predicts thrust by ~2–4× vs the (now primary-source-verified) experiment, because
it misses the viscous/transitional losses. Stage 13 adds the transition model that closes that
gap and re-runs the unsteady-airfoil ladder rung with the Stage-12 U95 machinery, turning the
Stage-11/12 CONCERN into a validated (or honestly-bounded) result.

## Deliverables

1. **Transition model: `kOmegaSSTLM` (γ-Reθ)** in the OpenFOAM adapter — a transitional turbulence
   path alongside the laminar + `kOmegaSST` ones. Pin + document (ADR). Verify on a transitional
   flat-plate / airfoil (e.g. Schubauer-Klebanoff or a T3-series ERCOFTAC case) that transition
   onset lands within band.
2. **Resolve the plunging-foil over-prediction (Stage-11/12 carry-over).** Re-run the rigid
   plunging NACA-0012 with `kOmegaSSTLM` (and/or **re-anchor at a pre-bifurcation St 0.2–0.3**,
   where the experiment IS measured ~0.2). Compose a full-U95 `ReportableResult`
   (`scripts/stage12_reportable.py`) against the **corrected** HG reference. Target: the
   over-prediction closes to within the (honest, ~15–40 % model-form) band, or the residual gap is
   root-caused (2-D-vs-3-D span; teardrop-vs-NACA geometry) and documented. **No tolerance
   relaxation.**
3. **Pitching-airfoil dynamic stall vs McCroskey** (NASA TM-84245): a pitching NACA-0012, validate
   the force/moment loop (lift + moment hysteresis) within band — the transitional unsteady
   anchor. Full-U95 `ReportableResult` (batch-means over the converged cycles).
4. **NACA-0012 transient-mean debt (Stage-11 NO-GO):** the real fix — a **sharp-TE** TE-region
   remesh transient-mean (no base drag) OR the SU2 cross-check (ADR-017's blunt-TE budget shows
   blunt-TE cannot reach 3 %). Reach the 3 % Cd tolerance or document the residual with U95.
5. ADR(s) for the transition-model pin + the unsteady-airfoil decisions. Post-stage handoff +
   author the **Stage-14 prompt** (`docs/handoff-bundle/STAGE-14-rigid-flapping-wing.md` —
   prescribed-kinematics flapping vs Dickinson 1999 / Wang-Birch-Dickinson 2004). Tag `v0.0.13`.

## The GO/NO-GO gate

**GO** = the transition model reproduces a canonical transition-onset case within band, AND at
least one unsteady-airfoil rung (the re-anchored plunging foil OR the pitching-airfoil dynamic
stall) carries a full RSS-composed `U95` into a `ReportableResult` that clears its experiment
anchor — with the transitional path demonstrably improving on the Stage-12 laminar over-prediction.

**NO-GO** = if `kOmegaSSTLM` cannot reproduce transition onset, or the unsteady-airfoil case cannot
be brought within band even with transition + a defensible re-anchor, STOP and document — the
flapping flagship (Stage 14) must not build on an untrusted transitional path. Investigate the
physics (mesh y+, transition Reθ tuning, 2-D-vs-3-D), never relax the tolerance.

## POST-STAGE HANDOFF (mandatory)

Write `docs/handoffs/STAGE-13-transition-and-unsteady-airfoil-DONE-YYYY-MM-DD.md` (full frontmatter
+ 10 sections, `.claude/rules/handoff-discipline.md`). Emphasize: the transition-model pin + its
onset verification; the plunging-foil resolution (transition and/or re-anchor) with the composed
U95; the pitching-airfoil dynamic-stall result. Confirm the **Stage-14 prompt exists**. Tag `v0.0.13`.
