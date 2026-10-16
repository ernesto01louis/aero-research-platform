---
stage: 22
stage_name: "Stage 22 — Foundation I: An Honest V&V Report"
status: partial
date_started: 2026-10-16
date_completed: 2026-10-16
session_duration_hours: 0.5
claude_code_version: "2.1.150 (Claude Code)"
model: "claude-fable-5-1, then claude-opus-5-5"
git_sha_start: 2235560dd217c4938655d38c382e48154bb533f9
git_sha_end: 2235560dd217c4938655d38c382e48154bb533f9
stage_tag: v0.1.1
next_stage: 23
next_stage_name: "Stage 23 — Foundation II: Provenance You Can Trust"
---

# Stage 22 — Foundation I: An Honest V&V Report — PARTIAL (opened 2026-10-16)

> **Stage 22 is `partial`.** This file is kept current from the first commit to the close, as the
> Stage-21 handoff was. `git_sha_end` is the `main` commit the stage opened on until the release
> PR's bump commit replaces it.
>
> - **The prompt of record** is `docs/handoff-bundle/STAGE-22-foundation-honest-vv-report.md`.
> - **The charter** is ADR-051 (accepted 2026-10-16). Its operator decisions bind this stage:
>   **D2 = (b)**, a per-solver-stack V&V verdict; **D4 = `v0.1.1`**, a patch version per
>   foundation stage.
> - **No campaign compute.** Never relax a tolerance. No case becomes `pass` without a passing run.
>   Stage 20 stays closed. PR #21 is left alone.

## 1. Deliverables status

| # | Deliverable (verbatim from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | Bookkeeping (first commit) | ✅ | `.aero-stage` 22, Dependabot prefix `ci(stage-22)`, this handoff, README regenerated |
| 2 | The report reads the truth | ❌ | not started — per-case MLflow query, explicit paging, fake-client tests |
| 3 | Typed status and the verdict | ❌ | not started — `DashboardEntry.status` Literal, per-stack verdict (D2 (b)) |
| 4 | No V&V workflow is green when it measured nothing | ❌ | not started — audit of the five workflows; see the audit table in §5 for the measured state at open |
| 5 | The per-case table | ❌ | the "before" table is below; the "after" table and the cross-check follow deliverable 2 |
| 6 | The close: `v0.1.1` (D4) | ❌ | release PR, then the operator cuts the tag |

(✅ = done, ⚠️ = partial, ❌ = not done / blocked)

### The per-case table at open (the "before" table)

Read on 2026-10-16 from MLflow `http://192.168.2.234:5000`, experiment `aero-provenance`
(2406 runs; 2388 on 2026-10-15, the 18 newer ones are `vv-smoke` runs). The windowed report
(`search_runs(..., max_results=500)`) and a full three-page pagination of the experiment were
both taken read-only. The per-case query `tags.validation_tag = '<case>'` (newest first, one
result) agreed with the pagination on all 25 cases: **0 mismatches**.

| Case | Windowed report (today) | True latest run | Run id | Run date | git sha |
|---|---|---|---|---|---|
| blasius_flat_plate | pass | pass | `8431062d1cdb48768f0fc7a4af25ceab` | 2026-10-16 | `2235560d` |
| cylinder_strouhal_re100 | pass | pass | `e67dc4f820854354a3a494c346375725` | 2026-10-15 | `e1f6378e` |
| laminar_airfoil_naca0012 | pass | pass | `2f5a0fa5d5ad44eb87f1fa5542699064` | 2026-10-15 | `e1f6378e` |
| oscillating_cylinder_lockin | pass | pass | `2d8f6dfc97ed4f8c8b19b96255ad89ef` | 2026-10-11 | `bc1384ad` |
| flat_plate_te | fail | fail | `bfbdbfea71254ad192b38e68f4450d5c` | 2026-10-15 | `e1f6378e` |
| t3a_flat_plate_transition | **missing** | pass | `b6c4783e82414060afa77c7c38374798` | 2026-07-06 | `0e0a0a7d` |
| turek_hron_cfd2 | **missing** | pass | `c0dfea184dea497db9bc94050397e8c2` | 2026-07-26 | `6abf00f6` |
| turek_hron_cfd3 | **missing** | pass | `650ac4358365468f9db9e067b4681bec` | 2026-07-26 | `6abf00f6` |
| naca0012_verification | **missing** | fail | `e8b29a4fb04645608ccb0203cf178002` | 2026-06-10 | `db413256` |
| plunging_airfoil_hg2007_st03 | **missing** | fail | `536d836e32a44afe8bc6484850d86006` | 2026-07-06 | `10328343` |
| plunging_airfoil_hg2007_st03_lm | **missing** | fail | `c6b85732905c440b97932240108ae76d` | 2026-07-06 | `10328343` |
| bump_2d | missing | no run | — | — | — |
| flapping_wing_wbd2004 (+`_advanced`, `_delayed`) | missing | no run | — | — | — |
| hg2007_rigid_foil | missing | no run | — | — | — |
| plunging_airfoil_hg2007 (+`_st02`, `_st02_lm`) | missing | no run | — | — | — |
| turek_hron_fsi3 | missing | no run | — | — | — |
| hg2007_flexible_foil (deferred, ADR-046 S4) | missing | no run | — | — | — |
| naca0012_transonic, onera_m6 (SU2, frozen, ADR-013) | missing | no run | — | — | — |
| taylor_green_p3_32, periodic_hill_2d (PyFR, frozen, ADR-013) | missing | no run | — | — | — |

Totals: the windowed report says **5 pass / 1 fail / 20 missing**; the truth is **7 pass / 4 fail /
14 no run**. Every gated run of a registered case carries `solver_version = "OpenFOAM-ESI v2412"`
(1516 runs); no SU2, PyFR or preCICE-tagged gated run has ever been logged.

`validation_tag` values that are not registered cases, and never enter the verdict: `bump_2d-sweep`
(369), `naca0012_verification-sweep` (63), `oscillating_cylinder_lockin-sweep` (2), about 90
Stage-17 `s17*-sweep` tags, and the tier names `thesis-grade` (1) and `validated` (4), which are
reportable records written by the Stage-12/13/14 scripts and carry no `vv_status`.

## 2. Decisions made

- **D2 = (b), a per-solver-stack verdict** (operator, 2026-10-16, with ADR-051's acceptance).
  Frozen-optional cases (SU2: `naca0012_transonic`, `onera_m6`; PyFR: `taylor_green_p3_32`,
  `periodic_hill_2d`; ADR-013) and the deferred `hg2007_flexible_foil` (ADR-046 S4) stay registered
  and visible with a typed status, are never `pass`, and no longer gate a stack they do not
  measure. Rejected: (a) running them (SU2 fails at startup on the runner, PyFR has no GPU runner);
  (c) removing them (hides them, the failure mode the registry-driven report exists to prevent).
  Implementation choices under D2, taken at stage open:
  - the preCICE-coupled cases (`turek_hron_fsi3`, `hg2007_rigid_foil`) gate the **openfoam** stack,
    which is what ADR-051's Stage-24 arithmetic (9 no-run + 4 failing + 7 passing = 20 active cases)
    already assumes; the fluid solver is OpenFOAM;
  - a case's status comes from the newest run **on its own stack** (the `solver_version` tag): the
    TMR cases are also run through SU2 under the same `validation_tag`, so a newer off-stack run
    must never be attributed to the OpenFOAM stack (a no-op on today's data, see §1);
  - `frozen` and `deferred` replace `missing` only when a case has no run; a real run's status is
    always shown, and a frozen stack's verdict is never green by absence.
- **D4 = `v0.1.1`** (operator, 2026-10-16): a patch version per foundation stage, through the
  ADR-049 R3 release PR, tag gate and readiness check. A GitHub Release only if the operator chooses.
- **Documented-NO-GO active-stack cases are deselected with words in CI** (operator, 2026-10-16,
  plan review). Once a solver failure can no longer hide behind `xfail`, a case whose solve cannot
  complete (NACA 0012 verification, ADR-017) is deselected by an explicit `unmeasurable` marker on
  PR/push and nightly jobs, and the job summary names it and why. The required check stays a
  regression gate over measurable cases; the report carries the truth. Rejected: a nightly that
  attempts them and is red daily; attempting them everywhere, which turns the required
  `vv-required` context red until Stage 25.
- **`vv-transonic` becomes dispatch-only** (operator, 2026-10-16, plan review), the H-19 pattern
  already applied to `vv-scale-resolving`. It fails loudly on a solver failure; the SU2 stack is
  frozen-optional, so a nightly that is red every night was rejected.

## 3. Deviations from the stage plan

- **The brief's ONERA M6 explanation is not what the logs show.** ADR-051 §1 and the prompt say the
  mesh was never fetched because `dvc pull` printed "skipped". Read-only evidence at stage open:
  - "`onera_m6: solver failed (rc=1)`" can only be raised after the SU2 adapter copied the mesh and
    parsed its element count; a genuinely missing mesh reads "SU2 mesh asset not found" (seen in
    `vv-required` run 38733522747, which has no pull step at all);
  - `bump_2d` on SU2, which uses an analytic mesh and no DVC asset, dies with the same rc=1 in
    `vv-smoke` (run 38770065555) and `vv-required`;
  - the bare `dvc pull` exits 1 because it also targets `data/datasets/drivaerml/cases.dvc`
    (380 GB on the `aero-nfs` remote, ADR-011), whose directory object is absent from the default
    `aero-minio` remote (`dvc status -c` from the host confirms it); DVC fetches what it can,
    including the mesh, raises `CheckoutError` at the end, and `|| echo "dvc pull skipped (no
    remote configured)"` relabels that — the remote is configured, `--quiet` hides the message.
  - `OneraM6.evaluate()` always raises (`aero/vv/transonic/onera_m6.py:79-88`): the eta = 0.44
    Cp slice is unimplemented, so the case could not pass or fail even after a successful solve.

  Deliverable 4 therefore fixes the pull (targeted, un-quieted, fail-loud) and makes the SU2
  failure visible, and records the SU2 startup failure as an SU2-stack item instead of fixing a
  frozen-optional solver. PR #21 only moves the `aero-nas` endpoint and is unrelated.

## 4. Environment / dependency / schema changes

- None yet.

## 5. CI/CD changes

- None yet. **The audit table at open** (what each workflow measured in its last run, read from
  the run logs on 2026-10-16; "what changed" is filled in by deliverable 4):

| Workflow | Last run | Conclusion | What it measured | What changed |
|---|---|---|---|---|
| `vv-transonic` (nightly) | 38720763677, 2026-10-15 | success | **Nothing.** `test_onera_m6_cp_at_eta_044` SKIPPED on "solver failed (rc=1)"; `test_transonic_naca0012_cd_within_tolerance` XFAIL in 8 s. Test step 23 s. | — |
| `vv-smoke` (push/PR) | 38770065555, 2026-10-15 | success | 3 passed (blasius, cylinder, laminar airfoil); 2 SKIPPED on rc=1 (bump_2d SU2, with a reason text that says "reference data not present"; onera_m6); 5 XFAIL, of which only the OpenFOAM flat plate measured and logged a `fail`; 72 deselected. 31 min. | — |
| `vv-smoke` (nightly) | 38714744692, 2026-10-15 | success | 3 passed; 2 skipped (same); 7 xfailed; 1 XPASS (`test_bump_gci_mesh_sweep`). | — |
| `vv-required` (required) | 38874315715, 2026-10-16 | success | Nothing: "V&V not relevant — passing trivially" (docs-only PR). On a relevant PR (38733522747): 3 passed, 2 skipped on rc=1 / missing mesh, 5 xfailed. | — |
| `moving-vv` (weekly) | 38124230055, 2026-10-11 | failure | Honest: `oscillating_cylinder_lockin` pass (run `2d8f6dfc`), then `plunging_airfoil_hg2007` timed out at 14400 s, `BenchmarkError rc=124`, exit 1. Five straight weekly failures. | — |
| `vv-scale-resolving` (dispatch) | 38275750272, 2026-10-12 (pre-H-19 schedule) | success | Nothing: `have_gpu=false` is hard-coded, both GPU jobs skipped. No run since H-19 made it fail loudly. | — |

No V&V workflow writes `$GITHUB_STEP_SUMMARY` at open.

## 6. Gotchas discovered

- **Stage open is one commit by construction.** The Stop hook requires a Stage-22 handoff as soon as
  `.aero-stage` reads 22, and `tests/unit/test_workflow_hygiene.py` requires the Dependabot prefix
  to equal `ci(stage-22)`: `.aero-stage`, the prefix, this file and the README must land together.
- **The report's non-`--latest` mode and the window.** `vv-smoke` logs four cases on every push
  (18 runs between 2026-10-15 and 2026-10-16), so any fixed window is filled within days.

## 7. Open items for the next stage (and beyond)

- **This stage:** deliverables 2–6; the Stage-23 prompt
  (`docs/handoff-bundle/STAGE-23-foundation-provenance.md`) is **not yet written**.
- **Stage 23 (provenance):** a bare `dvc pull` can never succeed in this repository because the
  inputs are spread over several remotes (DrivAerML on `aero-nfs`, small assets on `aero-minio`);
  a content-addressed `dvc_input_hash` (O-07) must be defined per input, not per repository sync state.
- **Stage 24 (run the registry):** solver failures log nothing to MLflow (the runner raises before
  `_log`), so the report cannot show them; decide whether a failed solve becomes a logged `fail`.
  `bump_2d` has no single-grid test and has only ever run as GCI sweeps (369 `-sweep` runs).
- **Stage 25 (turbulent cases):** the bump GCI sweep XPASSed on the 2026-10-15 nightly, so its
  `xfail` may be stale.
- **SU2 stack (frozen-optional):** SU2_CFD dies with rc=1 at startup on `aero-build` for every case;
  `OneraM6.evaluate()` is unimplemented.

## 8. Pointers for the next session

- **Read first:** this file, the prompt of record, ADR-051, ADR-005, the Stage-21 handoff §6–§7.
- **Do not re-read:** the Stage-20 campaign records.
- **Run first:** `PATH=.venv/bin:$PATH pytest -q tests/unit`;
  `bash scripts/check_handoff_exists.sh; echo $?` (0); `scripts/regenerate_status.sh --check`;
  `gh pr list`; the hard-don't checks (no ADR-045 records, the `stage-20-evidence-2026-09-20` tag,
  unfilled B-sentinels).

## 9. Artifacts produced

- This handoff.

## 10. Confidence / risk

- **High confidence:** the per-case table in §1 (two independent read-only reads agree on all 25
  cases).
- **Medium confidence:** the cause of the SU2 rc=1 is not yet known; it is diagnosed in deliverable 4.
- **Outstanding risks:** the self-hosted queue paces every PR (about 45 min per CI cycle); the
  release close needs all 12 required contexts green and the operator's tag.
