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
| 2 | The report reads the truth | ✅ PR B | `aero/vv/report.py`: one MLflow query per registered case and stack prefix (no window); the history listing pages the whole experiment and states its bound; 25 fake-client tests in `tests/unit/test_vv_report.py`, incl. the four the prompt names |
| 3 | Typed status and the verdict | ✅ PR B | `aero/vv/status.py` (`VVStatus` Literal, `stack_verdicts`), `aero/vv/stacks.py` (the 25-case stack table, loud on drift); `DashboardEntry.status` typed; one verdict per stack in the text and the HTML; CLAUDE.md, ADR-005 (dated scope note) and `docs/vv/output-validity-bar.md` cite ADR-051 D2 |
| 4 | No V&V workflow is green when it measured nothing | ✅ PR C | every `dvc pull` targeted and fail-loud; only a tolerance miss may `xfail` (`raises=AssertionError`); no skip on a solver error; a not-ready cluster fails in CI (`AERO_VV_REQUIRE_CLUSTER=1`); every V&V job writes a step summary of what it measured and what it did not; `vv-transonic` dispatch-only; hygiene tests pin all of it. The audit table is in §5; the diagnostic dispatch is pending |
| 5 | The per-case table | ✅ | before and after tables below; `scripts/vv_report_crosscheck.py` (a full pagination, independent of `aero.vv.report`) agrees case for case: status and run id on all 25 |
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

### The per-case table after the fix (deliverable 5)

The fixed `aero vv report --latest`, run on branch `stage-22-honest-report` against live MLflow at
2026-10-16T09:22Z (read-only). The four smoke cases' run ids differ from the "before" table only
because `vv-smoke` logged newer runs in between; every other run id is the same.

```text

  V&V report: the newest run of every registered case on its own solver stack
  (one MLflow query per case and stack prefix; no window)

  25 registered case(s): 7 pass, 4 fail, 9 missing, 4 frozen, 1 deferred

  stack openfoam: OpenFOAM-ESI v2412, including the preCICE-coupled OpenFOAM cases (active; ADR-051 D2)
    [GREEN ] blasius_flat_plate                 pass     9cff5db048014808bd6c06d1240c2da3  2026-10-16  cf3a603a7148  OpenFOAM-ESI v2412
    [RED   ] bump_2d                            missing  no run
    [GREEN ] cylinder_strouhal_re100            pass     646bdabbdc52495386ef3905d5ad2328  2026-10-16  2235560dd217  OpenFOAM-ESI v2412
    [RED   ] flapping_wing_wbd2004              missing  no run
    [RED   ] flapping_wing_wbd2004_advanced     missing  no run
    [RED   ] flapping_wing_wbd2004_delayed      missing  no run
    [RED   ] flat_plate_te                      fail     c5bb17e5f02847db8021463311ea9524  2026-10-16  2235560dd217  OpenFOAM-ESI v2412
    [DEFER ] hg2007_flexible_foil               deferred no run; deferred (ADR-046 S4), gates nothing
    [RED   ] hg2007_rigid_foil                  missing  no run
    [GREEN ] laminar_airfoil_naca0012           pass     9a4fe535006046fa88dfeeb1daf61c06  2026-10-16  2235560dd217  OpenFOAM-ESI v2412
    [RED   ] naca0012_verification              fail     e8b29a4fb04645608ccb0203cf178002  2026-06-10  db413256a8a4  OpenFOAM-ESI v2412
    [GREEN ] oscillating_cylinder_lockin        pass     2d8f6dfc97ed4f8c8b19b96255ad89ef  2026-10-11  bc1384adbf77  OpenFOAM-ESI v2412
    [RED   ] plunging_airfoil_hg2007            missing  no run
    [RED   ] plunging_airfoil_hg2007_st02       missing  no run
    [RED   ] plunging_airfoil_hg2007_st02_lm    missing  no run
    [RED   ] plunging_airfoil_hg2007_st03       fail     536d836e32a44afe8bc6484850d86006  2026-07-06  103283432393  OpenFOAM-ESI v2412
    [RED   ] plunging_airfoil_hg2007_st03_lm    fail     c6b85732905c440b97932240108ae76d  2026-07-06  103283432393  OpenFOAM-ESI v2412
    [GREEN ] t3a_flat_plate_transition          pass     b6c4783e82414060afa77c7c38374798  2026-07-06  0e0a0a7dbfc0  OpenFOAM-ESI v2412
    [GREEN ] turek_hron_cfd2                    pass     c0dfea184dea497db9bc94050397e8c2  2026-07-26  6abf00f62f2b  OpenFOAM-ESI v2412
    [GREEN ] turek_hron_cfd3                    pass     650ac4358365468f9db9e067b4681bec  2026-07-26  6abf00f62f2b  OpenFOAM-ESI v2412
    [RED   ] turek_hron_fsi3                    missing  no run

  stack su2: SU2 v8, frozen-optional (frozen; ADR-013)
    [FROZEN] naca0012_transonic                 frozen   no run; frozen-optional stack (ADR-013)
    [FROZEN] onera_m6                           frozen   no run; frozen-optional stack (ADR-013)

  stack pyfr: PyFR 1.15.0 (GPU), frozen-optional (frozen; ADR-013)
    [FROZEN] periodic_hill_2d                   frozen   no run; frozen-optional stack (ADR-013)
    [FROZEN] taylor_green_p3_32                 frozen   no run; frozen-optional stack (ADR-013)

  VERDICT openfoam: RED — not clear for production-tagged runs on this stack.
      4 fail: flat_plate_te, naca0012_verification, plunging_airfoil_hg2007_st03, plunging_airfoil_hg2007_st03_lm
      9 missing: bump_2d, flapping_wing_wbd2004, flapping_wing_wbd2004_advanced, flapping_wing_wbd2004_delayed, hg2007_rigid_foil, plunging_airfoil_hg2007, plunging_airfoil_hg2007_st02, plunging_airfoil_hg2007_st02_lm, turek_hron_fsi3
      shown but not gating (deferred): hg2007_flexible_foil
  VERDICT su2: FROZEN — never fully evaluated (frozen-optional, ADR-013); not clear for production-tagged runs on this stack.
      2 frozen: naca0012_transonic, onera_m6
  VERDICT pyfr: FROZEN — never fully evaluated (frozen-optional, ADR-013); not clear for production-tagged runs on this stack.
      2 frozen: periodic_hill_2d, taylor_green_p3_32

  A production-tagged run is gated by its OWN solver stack's verdict (ADR-005, scoped by ADR-051 D2).
  Stacks clear for production-tagged runs: none.
```

The independent read, `scripts/vv_report_crosscheck.py --against <the --json output of the same
minute>`, paging every run of the experiment:

```text
independent read: 2415 runs paged from http://192.168.2.234:5000, experiment 'aero-provenance'
  totals: 1 deferred, 4 fail, 4 frozen, 9 missing, 7 pass
AGREE: all 25 cases match /tmp/claude-0/-root/b9b9432a-eb74-451d-a326-1c869e8eb635/scratchpad/after.json (status and run id).
```

Before → after: **5 pass / 1 fail / 20 missing** → **7 pass / 4 fail / 9 missing / 4 frozen /
1 deferred**, with the openfoam stack RED and the su2 and pyfr stacks FROZEN. No case changed
status: the three hidden passes and three hidden failures are now shown, and the five cases that
cannot run on the active stack carry their D2 status instead of `missing`.

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

- New core modules, pure stdlib + pydantic: `aero/vv/status.py`, `aero/vv/stacks.py`,
  `aero/vv/report.py`, registered in `tests/unit/test_core_import_isolation.py` and the
  `import-platform-only` module list. `aero.vv` re-exports the status and stack names.
- `DashboardEntry` gained two required fields, `stack` and `disposition`; `status` is now the
  `VVStatus` Literal.
- `aero vv report` gained `--limit` (history mode only); `--html` now needs `--latest` (exit 2).
  `--json` is still a top-level array; each row gained `stack`, `disposition`, `solver_version` and
  `start_time`.
- New pytest markers (`pyproject.toml`): `stage_22`, `su2`, `unmeasurable`.

## 5. CI/CD changes

- **`import-platform-only`** imports the three new modules (PR B).
- **The V&V workflows** (PR C), against the audit table below:
  - every `dvc pull` is targeted and fail-loud; only `vv-transonic` pulls (the ONERA M6 mesh);
  - the active-stack jobs (`vv-required`, `vv-smoke`) select `... and not su2 and not
    unmeasurable`; the five SU2 tests are `su2`-marked and run only in the `vv-transonic` dispatch;
  - `AERO_VV_REQUIRE_CLUSTER=1` in every pytest V&V job: a not-ready cluster fails the suite;
  - every V&V job writes `$GITHUB_STEP_SUMMARY` (`scripts/vv_ci_summary.py` from the JUnit report
    and the deselection record), including the trivial `vv-required` branch and the GPU-less
    `vv-scale-resolving`;
  - `vv-transonic` lost its nightly schedule (operator, 2026-10-16) and became the SU2-stack job;
  - `vv-smoke`'s JSON step lost `|| echo "[]"`; its PR comment has a Stack column;
  - `tests/unit/test_workflow_hygiene.py` pins: targeted, un-quieted pulls with no `||`; no
    schedule on `vv-transonic`; a summary in all five; no `|| echo` in any V&V workflow; the
    cluster requirement and the JUnit report in the three pytest jobs; the active-stack selections.
- No required context changed.

**The audit table at open** (what each workflow measured in its last run, read from the run logs
on 2026-10-16), and what Stage 22 changed:

| Workflow | Last run | Conclusion | What it measured | What changed |
|---|---|---|---|---|
| `vv-transonic` (nightly) | 38720763677, 2026-10-15 | success | **Nothing.** `test_onera_m6_cp_at_eta_044` SKIPPED on "solver failed (rc=1)"; `test_transonic_naca0012_cd_within_tolerance` XFAIL in 8 s. Test step 23 s. | Dispatch-only; targeted fail-loud pull; runs all five `su2` tests; a solver failure FAILS; summary. |
| `vv-smoke` (push/PR) | 38770065555, 2026-10-15 | success | 3 passed (blasius, cylinder, laminar airfoil); 2 SKIPPED on rc=1 (bump_2d SU2, with a reason text that says "reference data not present"; onera_m6); 5 XFAIL, of which only the OpenFOAM flat plate measured and logged a `fail`; 72 deselected. 31 min. | SU2 tests deselected (`su2`); no pull; cluster required; summary lists the deselected cases in words; JSON step fails loudly. |
| `vv-smoke` (nightly) | 38714744692, 2026-10-15 | success | 3 passed; 2 skipped (same); 7 xfailed; 1 XPASS (`test_bump_gci_mesh_sweep`). | Same selection rules plus the GCI sweeps; summary. |
| `vv-required` (required) | 38874315715, 2026-10-16 | success | Nothing: "V&V not relevant — passing trivially" (docs-only PR). On a relevant PR (38733522747): 3 passed, 2 skipped on rc=1 / missing mesh, 5 xfailed. | Same selection as vv-smoke on PRs; cluster required; summary on both branches, the trivial one saying nothing was measured. |
| `moving-vv` (weekly) | 38124230055, 2026-10-11 | failure | Honest: `oscillating_cylinder_lockin` pass (run `2d8f6dfc`), then `plunging_airfoil_hg2007` timed out at 14400 s, `BenchmarkError rc=124`, exit 1. Five straight weekly failures. | No-op pull removed; per-case PASS/FAIL in the summary. Already honest. |
| `vv-scale-resolving` (dispatch) | 38275750272, 2026-10-12 (pre-H-19 schedule) | success | Nothing: `have_gpu=false` is hard-coded, both GPU jobs skipped. No run since H-19 made it fail loudly. | Summary says no GPU runner, PyFR cases `frozen`; no-op pull removed; DoMINO step guarded instead of `|| echo`. |

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
- `aero/vv/{status,stacks,report}.py`; the rewritten `aero/vv/dashboard.py` and `aero vv report`.
- `scripts/vv_report_crosscheck.py`, the independent full-pagination read.
- Tests: `tests/unit/{test_vv_report,test_vv_stacks,test_vv_dashboard_types,test_vv_report_crosscheck}.py`
  and the fake client `tests/unit/_fake_mlflow.py`.

## 10. Confidence / risk

- **High confidence:** the per-case table in §1 (two independent read-only reads agree on all 25
  cases).
- **Medium confidence:** the cause of the SU2 rc=1 is not yet known; it is diagnosed in deliverable 4.
- **Outstanding risks:** the self-hosted queue paces every PR (about 45 min per CI cycle); the
  release close needs all 12 required contexts green and the operator's tag.
