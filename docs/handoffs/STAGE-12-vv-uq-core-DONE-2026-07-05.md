---
stage: 12
stage_name: "Stage 12 — Verification & UQ Core"
status: complete
date_started: 2026-07-05
date_completed: 2026-07-05
session_duration_hours: 0
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-4-8
git_sha_start: "9e6e930e760d09032439879bc902e923af5b9c99"
git_sha_end: "8abec53b93877942efd6beea63e6b41f1321847e"
stage_tag: v0.0.12
next_stage: 13
next_stage_name: "Stage 13 — Transition + Unsteady-Airfoil Validation"
---

# Stage 12 — Verification & UQ Core — (2026-07-05)

> `git_sha_end` is provisional (reconcile to the squash-merge SHA at the `v0.0.12` tag — the
> Stage-08/10/11 pattern). Work landed on branch `stage-12/vv-uq-core`. **`status: complete`:**
> the `u95` machinery is built, tested, and **proven on real cylinder data** (the de-risk); both
> required CI gates are built + green locally; ADR-015 ratified. The cylinder thesis-grade
> `ReportableResult` with the **numerical** U95 term from the space+time GCI is finalized from the
> in-flight GCI run (§3/§7) — the statistical term + the full-U95 machinery are already validated
> end-to-end.

## 0. Headline

The platform now puts an **error bar** on every unsteady number: `U95 = RSS(u95_numerical,
u95_statistical, u95_input)`, composed end-to-end into a live `ReportableResult`. The new
**batch-means `u95_statistical`** estimator (NOBM + Sokal autocorrelation cross-check, PLATFORM-
NOT-HUB, no scipy) was **proven on the real oscillating-cylinder run** — 35 converged cycles →
`u95_statistical(Cd) = 0.0131`, reliable, `N_eff = 8.5` (it correctly catches the drag's real
cycle-to-cycle autocorrelation). Both CONSTITUTION invariants gained CI teeth: `small-signal-gate`
(Invariant 10) and `data-origin-fence` (Invariant 11), both on `ubuntu-latest` (runner-
independent → required-safe). **ADR-015 ratified** (Invariants 10+11 constitutional). The
Stage-11 plunging-foil CONCERN was **verified against the primary source** (Heathcote's PhD
thesis) and **re-attributed**: the reference was ~right (~0.2), our 2-D laminar solve
**over-predicts** — a Stage-13 root-cause item, tolerance not relaxed.

## 1. Deliverables status

| # | Deliverable (from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | `u95_statistical` batch-means estimator | ✅ | `aero/vv/statistical_uncertainty.py`; NOBM primary + Sokal τ_int→N_eff cross-check; Student-t committed table; relative dead-signal guard; soft `reliable` flag. 9 host tests. **Proven on real cylinder data** (de-risk: Cd 0.0131 reliable, Cl 0.0039). |
| 2 | Full U95 composition end-to-end | ✅ | `aero/vv/reportable_compose.py` (5 tests) + `scripts/stage12_reportable.py`. Composes RSS U95 into a `ReportableResult`, MLflow-logged; conservative thesis-grade tag policy. Validated end-to-end on the cylinder run (thesis-grade, u95_total 0.024 w/ placeholder GCI). |
| 3 | Invariant-10 `small-signal-gate` CI (required) | ✅ | `.github/workflows/small-signal-gate.yml` on ubuntu-latest; `tests/stage_12/test_small_signal_gate.py` + committed fixture. Promote-to-required via `gh api` at finalize (§5). |
| 4 | Invariant-11 `data_origin` fence (required) | ✅ | `data_origin` on Sample/cert (fail-closed default `foreign`), write-once taint, schema validator (foreign + validated/production **unconstructible**), promote refusal, 4 loaders tagged. `data-origin-fence.yml` + `tests/stage_12/test_data_origin.py`. ADR-015 constitution merge = **ratified** (proposed→accepted). |
| 5 | Rigor follow-ups (HG verify, clean-SHA, GCI) | ✅/⚠️ | **HG reference verified against the primary source** → corrected (foil over-predicts, not the reference); combined **space+time GCI** for the cylinder (`scripts/stage12_cylinder_gci.py` + `refined_dt`) — run in-flight (§7). Foil GCI **cut** (operator decision: light treatment, foil is a CONCERN regardless). |
| 6 | ADR + handoff + Stage-13 prompt + tag | ✅/⏳ | ADR-020 (UQ core); this handoff; **Stage-13 prompt exists** (`docs/handoff-bundle/STAGE-13-transition-and-unsteady-airfoil.md`). Tag `v0.0.12` at finalize. |

## 2. Decisions made

- **NOBM primary + Sokal τ_int cross-check, soft `reliable` flag (ADR-020).** Rejected a *hard*
  N_eff floor / cross-check raise: the Sokal window structurally bounds N_eff ≳ 4.8, and few-batch
  `s_batch` is noisy, so a hard gate spuriously NO-GO'd a plausible converged limit cycle in
  testing. The estimator trusts `cycle_detection` for stationarity and hard-raises only on
  not-converged / N<8 / dead-signal; "N_eff too small" → the soft flag, which the **composer**
  treats as blocking for thesis-grade. That is where the "STOP" belongs.
- **Fail-closed `data_origin="foreign"` default + a schema validator** making a foreign +
  validated/production cert unconstructible on every path (not just a `promote` refusal) — the
  load-bearing Invariant-11 guard. Consequence: DoMINO-on-DrivAerML (foreign) can no longer be
  `validated`; the existing Cd-gate/compare tests were re-pointed at synthetic platform-validated
  data (the machinery test is orthogonal to data-origin).
- **Cylinder is the thesis-grade GO vehicle; foil is a documented CONCERN (light treatment)** —
  operator decision, after HG verification showed the foil over-predicts. Report the cycle-mean
  **Cd** (a genuine time-average with a batch-means term) anchored by the lock-in Strouhal.
- **Two-arm space+time GCI** (spatial 3-grid + temporal 2-grid bound, RSS) — Celik/ASME GCI is
  single-parameter; `refined_dt` sweeps the Courant-driven timestep that `refined()` cannot touch.
- **vv-required CI selector fix (on the merged Stage-11 PR):** the multi-hour moving cases were
  timing out the required check; excluded via a `moving` marker (the `mesh_sweep` precedent).

## 3. Deviations from the stage plan

- **Foil scope reduced to a light treatment** (operator-approved): HG verification (via the
  primary-source thesis) reversed the Stage-11 assumption — the reference is ~right (~0.2), our
  2-D laminar C_T≈0.96 **over-predicts** ~2–4×. The foil is composed as a CONCERN (`validated`,
  failing anchor, large `u95_input≈40 %`); a full foil GCI was **cut** (it can't be thesis-grade
  regardless). Root-cause (2-D-vs-3-D / transitional; low-St re-anchor) → Stage 13.
- **`aero vv reportable` as a script, not a typer subcommand:** the run-dir → batch-means pipeline
  is solver-specific and derives from a multi-hour run (like `stage11_moving_vv.py`), so it ships
  as `scripts/stage12_reportable.py`. A thin CLI wrapper is a cheap follow-up.
- **Cylinder GCI numerical term finalized post-handoff-write:** each moving solve is ~84 min serial
  (MPI blocked); the space+time GCI (~3.3 h) was launched and runs in-flight. The statistical term
  + the full-U95 machinery are already validated (de-risk + the reportable script on the real run).

## 4. Environment / dependency / schema changes

- New `aero/vv/{statistical_uncertainty,reportable_compose}.py` (core: stdlib+numpy+pydantic).
- `Sample`/`CertificateOfValidity` gain `data_origin: Literal["platform-validated","foreign"]`;
  `Surrogate` gains `_data_origin` (write-once) + a `data_origin` property; `as_mlflow_tags` adds it.
- `OscillatingCylinderLockin.refined_dt` (temporal-GCI seam). New `moving` pytest marker.
- New scripts: `stage12_cylinder_gci.py`, `stage12_reportable.py`. No new pyproject extras.
- Reference data corrected: `data/references/unsteady/plunging_airfoil_hg2007/{thrust.csv,reference.md}`.

## 5. CI/CD changes

- **New required-candidate gates** (ubuntu-latest): `small-signal-gate.yml` (Invariant 10),
  `data-origin-fence.yml` (Invariant 11). **Promote both to required** via
  `gh api repos/ernesto01louis/aero-research-platform/branches/main/protection` after the Stage-12
  PR merges (record in `docs/operator/deferred-work-ledger.md`).
- `vv-required.yml` selector excludes `moving`-marked cases (fix landed on the merged Stage-11 PR).

## 6. Gotchas discovered

- **A "constant" tail isn't exactly constant** in float64 (`[x]*20` has std ~1e-16) — the
  dead-signal guard must be **relative**, not `== 0`.
- **Sokal-windowed N_eff floors ~4.8** for correlated data — a hard N_eff-floor NO-GO is
  unreachable/twitchy; make it a soft `reliable` flag + a composer policy instead.
- **`vv-required` timed out** because its selector swept in the two multi-hour moving cases; and a
  first fix updated the marker + comment but **not the selector line** — verify the selector, not
  just the markers.
- **DoMINO-on-DrivAerML is foreign** → under Invariant 11 it cannot be `validated`; the Stage-09
  Cd-gate tests needed re-pointing at synthetic platform-validated data (the gate logic is
  orthogonal to data-origin).
- The MLflow log timestamps are **local time** (CEST), the run clock is UTC — don't confuse them.

## 7. Open items for the next stage (and beyond)

- **Finalize the cylinder GO (this session's closing step):** when the space+time GCI
  (`scripts/stage12_cylinder_gci.py`, bg run) completes, `scripts/stage12_reportable.py
  oscillating_cylinder_lockin --run-dir <fine-grid dir> --gci-json data/vv/stage12_cylinder_gci.json`
  → the thesis-grade cylinder `ReportableResult` (Cd, real u95_numerical) logged to MLflow; also
  the foil CONCERN result (`--no-thesis-grade --u95-input-frac 0.4`). Reconcile the handoff numbers
  + `git_sha_end` + tag `v0.0.12`.
- **Stage 13 (Transition + Unsteady-Airfoil):** prompt written. **Resolve the foil over-prediction**
  (kOmegaSSTLM γ-Reθ + low-St re-anchor); pitching-airfoil dynamic stall vs McCroskey; the NACA-0012
  transient-mean debt (sharp-TE / SU2).
- **PR #21** (aero-nas DVC repoint) deferred — needs a branch-update; not needed for Stage 12.
- **CHANGELOG backfill debt:** v0.0.10/v0.0.11 got brief sections; full backfill is optional.
- A full 3-grid temporal GCI (vs the 2-grid bound) and a thin `aero vv reportable` CLI wrapper.

## 8. Pointers for next session

- **Read first:** this file + ADR-020 + ADR-015 + the Stage-13 prompt + `git log 9e6e930..`.
- **Run first to verify:** `pytest tests/vv tests/stage_12 tests/stage_09 tests/unit -q -m "not slow"`
  (all green), `mypy aero`, `ruff check aero tests scripts`. The estimator is proven on the real
  cylinder run at `/mnt/aero-nfs/runs/oscillating_cylinder_lockin-20260705-073955`.
- **Do not re-read:** the merge-saga CI-debug transcripts (conclusions are in §6).

## 9. Artifacts produced

Commits on `stage-12/vv-uq-core` (`git log 9e6e930..HEAD`): the batch-means estimator; the
composer; the small-signal-gate; the refined_dt seam + GCI driver; the data_origin/Invariant-11
fence; the reportable script; the HG-reference correction; ADR-020 + ADR-015 ratification +
CONSTITUTION + CHANGELOG. New code: `aero/vv/{statistical_uncertainty,reportable_compose}.py`,
`aero/surrogates/**` (data_origin), `scripts/stage12_{cylinder_gci,reportable}.py`,
`tests/stage_12/*`, two CI workflows, ADR-020, this handoff, the Stage-13 prompt. **MLflow
(aero-mlflow):** the space+time GCI grids + the composed cylinder/foil `ReportableResult` artifacts
(stage=12) — finalized on GCI completion.

## 10. Confidence / risk note

High confidence: the estimator (proven on real + synthetic data, lint/type-clean), the composer +
its conservative tag policy, both CI gates (host suites green), the Invariant-11 schema guard, the
HG re-attribution (three research threads, two on the primary source). The batch-means term is the
GO's hardest part and it is **retired** (the de-risk). Lower confidence: the exact cylinder
`u95_numerical` magnitude (pending the in-flight GCI; the coarser grids could in principle
under-resolve — the forced lock-in is robust, so the risk is low). The foil is honestly a CONCERN
(over-prediction), not a claimed GO. **Bus-factor / finalize note:** the closing steps are
procedural (GCI collect → compose → MLflow → PR → gate promotion → tag) and documented in §7.
