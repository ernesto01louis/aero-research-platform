# ADR-031 — ADR-025 reconciliation, DRAFT ratification, and the gp_bootstrap member family

- **Status:** accepted
- **Date:** 2026-07-24
- **Deciders:** Operator (Louis Ernesto Schulte Moredo, via approved Stage-17 plan); Claude Code
  agent (Stage 17)
- **Stage:** 17

## Context and problem statement

The STAGE-17 prompt opens with a RECONCILE-FIRST mandate: the ADR-025
anti-surrogate-exploitation stack (EnsembleSurrogate, calibration, trust region,
uncertainty-routed infill) was authored inter-stage on the local-only branch
`feat/stage-14-anti-surrogate-exploitation` (head 5a416e5) together with a DRAFT
surrogate-stage prompt whose ratify-or-amend is a Stage-15 handoff obligation. Main had
meanwhile moved four commits ahead (Stage-14 flapping merge, Stage-15 optimizer, Stage-16
certification, ADR-027 ratification) and renumbered the surrogate stage from 16 to 17.
Three questions had to be settled before any Stage-17 code: how to merge without losing
either line's work, what the DRAFT's clauses resolve to against the committed STAGE-17
prompt, and what ensemble member family the own-data surrogate uses.

## Decision outcome

### 1. Merge mechanics (PR #33)

The branch was pushed to origin verbatim for preservation, then merged with `--no-ff`
into `stage-17-reconcile`. End-state resolutions:

| File | Resolution |
|---|---|
| `aero/vv/reportable.py`, `aero/vv/reportable_compose.py` | **main** — preserves ADR-029 (`IndependentDeltaU95`, `compose_independent_improvement`); the branch's hardening was already on main verbatim via #27 |
| `aero/adapters/openfoam/solver.py` | **main** — the branch retained pre-refactor inline loaders |
| `.aero-stage` | **main** (16), then bumped to 17 |
| `CLAUDE.md` | main's 21-stage / Invariant-12 text + the branch's anti-surrogate-exploitation doc block grafted (stale "Stage 16" references updated to 17) |

Post-merge proof: `git diff main -- <the three code files>` is empty; full suite,
mypy strict, ruff all green.

### 2. DRAFT ratify-or-amend disposition

The branch's `docs/handoff-bundle/STAGE-16-surrogate-accelerated-optimization.md` DRAFT
was **dropped in the merge** — the committed STAGE-17 prompt is its ratified successor.
Clause dispositions:

- **Deliverables 1-4** (own-data surrogate + cert/calibration; ADR-025-wired loop;
  Invariant-12 CFD verification; honest speed-up demo) → **RATIFIED** (carried verbatim
  into the STAGE-17 prompt).
- **Stage numbering (16)** → **SUPERSEDED** by the operator-ratified 21-stage map (17).
- **Calibration band [0.85, 0.99]** → **AMENDED to [0.85, 1.0]**, pre-campaign. The DRAFT
  itself marks the band "(ratify or amend this band)". At the Stage-17 holdout size
  (n ≈ 10-11 of a ~42-solve corpus at calibration_fraction 0.25), a PERFECTLY calibrated
  estimator lands empirical coverage 1.0 with probability 0.954^n ≈ 0.62 — the DRAFT's
  upper bound rejects calibrated surrogates more often than not. The over-wide-σ pathology
  the upper bound guarded is still caught by the accuracy gate (C2) and the reported
  z-diagnostics (D1: `mean_abs_z`, `std_z`). This amendment was recorded BEFORE any
  campaign solve ran; the band never moves after data exists.
- **GO "thesis-grade improvement delta"** → **REGISTERED READING**, pre-campaign: the
  speed-up race is to a pre-registered CFD-verified delta bar at the campaign grid,
  composed at the tier the substrate supports (`validated`). The Stage-16 verdict bounds
  the certification tier (honest NO-GO at order 0.465 < 0.5; the 393² rung is costed and
  ledgered, explicitly out of Stage-17 scope), so a literal thesis-grade GO gate would be
  unreachable regardless of the surrogate's merit — it would test the ledgered
  certification gap, not this stage's deliverable. Operator brief of 2026-07-24 states the
  Stage-17 definition of done as "a CFD-verified improvement delta in measurably fewer
  ground-truth CFD evaluations". The full gate block lives in ADR-032 and verbatim in
  `scripts/stage17_speedup_arm.py`.
- **Loop-config ADR obligation** → **RATIFIED**: ADR-032 carries the pre-registered
  trust-region/calibration/infill configuration.
- **Never-relax clause** → **RATIFIED unchanged.**

### 3. Member family: seeded bootstrap-GP (`gp_bootstrap`)

`aero/surrogates/gp_bootstrap.py::GPBootstrapMember` wraps the Stage-15 pure-numpy
Matérn-5/2 `GaussianProcess` as a `Surrogate`. Member diversity = seeded bootstrap
resampling (via the `seed + i` the ensemble already passes) + per-member length-scale
spread (0.20-0.40 on the unit cube). Bootstrap draws are deduplicated before the fit
(duplicates carry no information for an interpolating GP and degrade kernel conditioning).

Considered and rejected: **torch-MLP members** (the ADR-025 smoke-test path) — torch is
not installed on the training host, and 3-5 small MLPs on ~40 points in 2-D calibrate
poorly, which would flunk the pre-registered coverage gate for reasons unrelated to the
data; **a single GP with posterior std** — no member disagreement, no protection against
model-form error, and outside the ADR-025 ensemble contract.

Schema consequence (additive): `"gp_bootstrap"` joined the basis Literals in
`SurrogatePrediction`, `UncertaintyCalibration`, and `compute_uncertainty_calibration`;
`EnsembleSurrogate` gained `basis=`/`metric_name=` constructor parameters (defaults
`"deep_ensemble"`/`"cd_mae"` preserved — every pre-existing artifact and test is
unaffected) and a fail-loud gated `promote_to_validated()` (raises `PromotionRefused`
naming the failing gate; refuses foreign origin per Invariant 11; re-validates the
promoted cert through the full model validator so the foreign-cannot-be-validated guard
fires on every path).

### Consequences

- **Positive:** the ADR-025 stack is on main with zero rebuild; the DRAFT obligation is
  discharged with a written disposition; the member family can honestly pass a coverage
  gate on a ~40-point corpus; all schema changes are additive.
- **Negative:** the `gp_bootstrap` basis label adds a third uncertainty family to
  maintain; bagged GPs can under-disperse near dense data (mitigated by length-scale
  diversity; the pre-registered contingency is corpus extension, and the honest terminal
  outcome is the S7 NO-GO fallback).
- **Neutral / followup:** MC-dropout basis still has no producer (ledgered, ADR-025);
  the branch's `aero_progress` monitor and audit-reconciliation doc landed as-is.
