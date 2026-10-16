---
stage: 22
stage_name: "Stage 22 — Foundation I: An Honest V&V Report"
status: complete
date_started: 2026-10-16
date_completed: 2026-10-16
session_duration_hours: 4
claude_code_version: "2.1.150 (Claude Code)"
model: "claude-fable-5-1, then claude-opus-5-5"
git_sha_start: 2235560dd217c4938655d38c382e48154bb533f9
git_sha_end: cfad02aef26d6a509f4c92fc7fce7adf658e63e8
stage_tag: v0.1.1
next_stage: 23
next_stage_name: "Stage 23 — Foundation II: Provenance You Can Trust"
---

# Stage 22 — Foundation I: An Honest V&V Report — COMPLETE (v0.1.1 ready to tag)

> **Stage 22 is `complete`.** Deliverables 1–5 are merged on main (#71, #72, #73), and the release
> PR carries deliverable 6. `git_sha_end` is that PR's bump commit (`cfad02a`); the commit after it
> is docs-only (this handoff and the README), so the squash-merged commit that gets tagged has the
> same code tree, which `check_release_tag.sh` checks. **The tag `v0.1.1` is the operator's** (the
> agent's `git tag` is classifier-blocked): after the release PR merges,
> `release_readiness.py --gate release --online` must print `READY TO TAG v0.1.1`.
>
> **The verdict at the close is unchanged and RED.** No stack is clear for production-tagged runs:
> openfoam RED (7 pass, 4 fail, 9 missing), su2 and pyfr FROZEN. Stage 22 changed what the gate
> shows, never what a case is.
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
| 1 | Bookkeeping (first commit) | ✅ #71 | `.aero-stage` 22, Dependabot prefix `ci(stage-22)`, this handoff, README regenerated |
| 2 | The report reads the truth | ✅ #72 | `aero/vv/report.py`: one MLflow query per registered case and stack prefix (no window); the history listing pages the whole experiment and states its bound; 25 fake-client tests in `tests/unit/test_vv_report.py`, incl. the four the prompt names |
| 3 | Typed status and the verdict | ✅ #72 | `aero/vv/status.py` (`VVStatus` Literal, `stack_verdicts`), `aero/vv/stacks.py` (the 25-case stack table, loud on drift); `DashboardEntry.status` typed; one verdict per stack in the text and the HTML; CLAUDE.md, ADR-005 (dated scope note) and `docs/vv/output-validity-bar.md` cite ADR-051 D2 |
| 4 | No V&V workflow is green when it measured nothing | ✅ #73 | every `dvc pull` targeted and fail-loud; only a tolerance miss may `xfail` (`raises=AssertionError`); no skip on a solver error; a not-ready cluster fails in CI (`AERO_VV_REQUIRE_CLUSTER=1`); every V&V job writes a step summary of what it measured and what it did not; `vv-transonic` dispatch-only; hygiene tests pin all of it. The audit table and the diagnostic dispatch (run 38891472030) are in §5 |
| 5 | The per-case table | ✅ | before and after tables below; `scripts/vv_report_crosscheck.py` (a full pagination, independent of `aero.vv.report`) agrees case for case: status and run id on all 25 |
| 6 | The close: `v0.1.1` (D4) | ✅ ready to tag | the release PR: bump commit `cfad02a` (pyproject, the `uv.lock` root, CITATION `version` + `date-released`, CHANGELOG `[0.1.1] - 2026-10-16`, `docs/release/RELEASE-NOTES-v0.1.1.md`), then this docs-only commit. The tag is the operator's (§7) |

(✅ = done, ⚠️ = partial, ❌ = not done / blocked)

**PR map** (all squash-merged to main by the agent, each with all 12 required contexts green, as
the operator authorized):

| PR | Branch | What | Merge |
|---|---|---|---|
| #71 | `stage-22-open` | deliverable 1, bookkeeping | `389baf5` |
| #72 | `stage-22-honest-report` | deliverables 2, 3, 5 (FULL `vv-required`) | `8187c41` |
| #73 | `stage-22-honest-workflows` | deliverable 4, the ADR-051 erratum, the ledger, the Stage-23 prompt, the `regenerate_status.sh` test | `5f8e9c3` |
| release | `stage-22-release-v0.1.1` | deliverable 6: the v0.1.1 bump (FULL `vv-required`), then this handoff `complete` | — |

**Re-checked at the close** (2026-10-16T11:10Z, read-only): `aero vv report --latest` still gives
7 pass / 4 fail / 9 missing / 4 frozen / 1 deferred, and `scripts/vv_report_crosscheck.py` agrees
on all 25 cases (status and run id).

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
- **NACA 0012 verification is `unmeasurable`, on evidence.** Its OpenFOAM single-grid test and its
  nightly GCI sweep are marked. The shared run directory of the 2026-10-16 `vv-required` run
  (`/mnt/aero/runs/naca0012_verification-20261016-090809`) shows simpleFoam diverging:
  `forceCoeffs` reach ~1e133 at iteration 83 and the solve dies before evaluation. That is
  ADR-017's documented NO-GO ("diverges simpleFoam ~iter 83"). The old `xfail` swallowed the crash,
  so every job read "xfailed" while measuring nothing, and its newest MLflow run is from
  2026-06-10. The report still shows that `fail`; the tolerance is not relaxed; Stage 25 owns it.
  No other active-stack test is deselected: the OpenFOAM flat plate completes and logs a real
  `fail` every run, so it keeps a measuring `xfail`.
- **The readiness gate's limitation sentence was kept, not generalised.** `release_readiness.py`
  requires the v0.1.0 sentence ("... and v0.1.0 makes no flapping-wing optimization claim.")
  verbatim in every release's notes. It is still true, so the v0.1.1 notes carry it and add that
  v0.1.1 makes none either. Rejected: editing the gate in the release PR, which is a gate change
  with no reviewer of its own.
- **`vv-transonic` runs every `su2`-marked test**, not only the two transonic files: once the three
  TMR-through-SU2 tests are deselected from the active-stack jobs, this is the only place they are
  measured, which is what the `su2` marker's description says.
- **`AERO_VV_REQUIRE_CLUSTER=1`** (an addition the brief did not spell out): every cluster test
  skipped when its readiness fixture was false, so a runner that lost its cluster would have gone
  green measuring nothing. In the three pytest V&V jobs a not-ready cluster now fails, naming the
  missing pieces.
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
  frozen-optional solver. PR #21 only moves the `aero-nas` endpoint and is unrelated. The
  diagnostic dispatch then found the cause (§5): the adapter's own OpenMPI override names a
  component that does not exist in the container. ADR-051 §1 carries a dated erratum.
- **The NACA 0012 verification became `unmeasurable` before its PR ran**, not after, because the
  evidence was already on the shared NFS (§2). The plan had expected to learn it from PR C's first
  `vv-smoke` run.
- **Ride-along done:** the `scripts/regenerate_status.sh` unit test. **Ride-alongs ledgered:** H-34
  and H-35 (each a FULL `vv-required` run).

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

**Measured after the changes:**

| Run | Result | What it measured |
|---|---|---|
| `vv-smoke` on #73 (38886826849) | success | 3 passed (blasius, cylinder, laminar airfoil), 1 xfailed (the OpenFOAM flat plate, a measured 12.6 % Cf miss), 78 deselected, 0 skipped; summary and the stack-aware PR comment written |
| `vv-required` on #72 (38880338137) | success | the FULL run under the old selection, with the new report code |
| `vv-required` on #73 (38886826797) | success | trivially (no filter path changed); its summary says so in words |
| `vv-transonic` dispatch on main (38891472030) | **failure** | the targeted `dvc pull` of the ONERA M6 mesh succeeded; all five `su2` tests **FAILED** with `solver failed (rc=1)` and the solver-log tail; summary written |
| `vv-scale-resolving` dispatch on main (38891504151) | **failure** (by design) | nothing: no `gpu` runner; the summary says the PyFR cases are `frozen` |

**The SU2 diagnosis** (first diagnosis, not fixed; SU2 is frozen-optional). The log tail of every
SU2 case reads "It looks like MPI_INIT failed … `mca_bml_base_open() failed` → Returned "Not
found" (-13)", for framework `btl`, component `sm`. The SU2 container ships **Open MPI 4.1.6**,
whose shared-memory BTL is called `vader`; it has no `sm` (`ompi_info` inside
`/opt/aero/containers/su2-v8.sif` lists `ofi, openib, self, tcp, vader`). The adapter's Stage-06
override `OMPI_MCA_btl=self,sm` (`aero/adapters/su2/solver.py`, the `rc=53` socket fix) therefore
makes `MPI_Init` fail for every SU2 case. The likely fix is `self,vader`, which must be verified by
a dispatch before it is believed; it is ledgered, not applied.

## 6. Gotchas discovered

- **Stage open is one commit by construction.** The Stop hook requires a Stage-22 handoff as soon as
  `.aero-stage` reads 22, and `tests/unit/test_workflow_hygiene.py` requires the Dependabot prefix
  to equal `ci(stage-22)`: `.aero-stage`, the prefix, this file and the README must land together.
- **The report's non-`--latest` mode and the window.** `vv-smoke` logs four cases on every push
  (18 runs between 2026-10-15 and 2026-10-16), so any fixed window is filled within days.
- **A merged PR's `vv-smoke` keeps running** and holds a runner for ~30 minutes; it must not be
  cancelled. The delayed nightly `vv-smoke` (it started at 09:35 UTC, not 05:00) superseded main's
  push run through the workflow's own `cancel-in-progress`. Budget about 45–60 minutes per CI cycle.
- **A required check run can stick at `in_progress` with conclusion `success`** (the licence scan on
  #72). Re-running that hosted job (`gh run rerun <run> --job <id>`) cleared it.
- **Merge commits need Conventional Commit messages:** commit-lint checks every commit in a PR, so
  reword the merge of `main` into a stacked branch before pushing.
- **A version bump needs the local editable install refreshed** before the unit suite passes locally
  (`test_installed_version_is_the_pyproject_version` reads the installed metadata):
  `VIRTUAL_ENV=$PWD/.venv uv pip install --offline --no-deps -e .`. CI installs fresh.
- **`uv lock --offline` bumps only the root version line**, as in v0.1.0.
- **Never print `.dvc/config.local`**: it holds the DVC remote credentials. Check it with `ls`.
- **The case directories on the shared NFS are evidence** (`/mnt/aero-nfs/runs/<case>-<ts>/`): the
  NACA 0012 divergence was read from `postProcessing/forceCoeffs1/0/coefficient.dat`, read-only.
  The `naca0012-*` directories are the provenance-completeness job's walking-skeleton runs.

## 7. Open items for the next stage (and beyond)

- **The operator, to close Stage 22:**
  1. after the release PR merges, run
     `PATH=.venv/bin:$PATH python scripts/release_readiness.py --gate release --online` and expect
     `READY TO TAG v0.1.1 at <sha>`; then cut the annotated tag it prints and push it;
  2. decide whether to publish a GitHub Release (which mints a Zenodo version DOI);
  3. the README STATUS refresh follows the tag (one docs-only PR that drops "(not yet tagged)").
- **The Stage-23 prompt exists:** `docs/handoff-bundle/STAGE-23-foundation-provenance.md`. It lists
  six decisions to put to the operator at stage open.
- **Stage 23 (provenance):** a bare `dvc pull` can never succeed in this repository because the
  inputs are spread over several remotes (DrivAerML on `aero-nfs`, small assets on `aero-minio`);
  a content-addressed `dvc_input_hash` (O-07) must be defined per input, not per repository sync state.
- **Stage 24 (run the registry):** solver failures log nothing to MLflow (the runner raises before
  `_log`), so the report cannot show them; decide whether a failed solve becomes a logged `fail`.
  `bump_2d` has no single-grid test and has only ever run as GCI sweeps (369 `-sweep` runs).
- **Stage 25 (turbulent cases):** the bump GCI sweep XPASSed on the 2026-10-15 nightly, so its
  `xfail` may be stale.
- **SU2 stack (frozen-optional):** `MPI_Init` fails for every SU2 case because the adapter requests
  the `sm` BTL, which Open MPI 4.1.6 calls `vader` (§5); `OneraM6.evaluate()` is unimplemented.
  Both are ledgered; neither is Stage 23's work unless the operator invests in SU2.
- **Ledgered from this stage:** `docs/operator/deferred-work-ledger.md`, "Stage 22 — findings carried
  forward".

## 8. Pointers for the next session

- **Read first:** this file, the Stage-23 prompt, ADR-051 (with its §1 erratum), ADR-004, ADR-049.
- **Do not re-read:** the Stage-20 campaign records.
- **Run first:** `PATH=.venv/bin:$PATH pytest -q tests/unit`;
  `bash scripts/check_handoff_exists.sh; echo $?` (0); `scripts/regenerate_status.sh --check`;
  `gh pr list` (#21 only, left alone); `PATH=.venv/bin:$PATH aero vv report --latest` and
  `scripts/vv_report_crosscheck.py --against <its --json>`; the hard-don't checks (no ADR-045
  records, the `stage-20-evidence-2026-09-20` tag, unfilled B-sentinels).

## 9. Artifacts produced

- This handoff.
- `aero/vv/{status,stacks,report}.py`; the rewritten `aero/vv/dashboard.py` and `aero vv report`.
- `scripts/vv_report_crosscheck.py`, the independent full-pagination read.
- Tests: `tests/unit/{test_vv_report,test_vv_stacks,test_vv_dashboard_types,test_vv_report_crosscheck}.py`
  and the fake client `tests/unit/_fake_mlflow.py`.
- `scripts/vv_ci_summary.py` (the V&V job summaries) with `tests/unit/test_vv_ci_summary.py`; the
  `pytest_deselected` record and `AERO_VV_REQUIRE_CLUSTER` in `tests/vv/conftest.py`; the Stage-22
  hygiene rules in `tests/unit/test_workflow_hygiene.py`; `tests/unit/test_regenerate_status.py`.
- The five V&V workflows (§5); the `su2` and `unmeasurable` markers.
- Docs: ADR-005's dated scope note; ADR-051's dated erratum; CLAUDE.md's per-stack rule;
  `docs/vv/output-validity-bar.md`; the ledger section; the Stage-23 prompt.
- The release: `docs/release/RELEASE-NOTES-v0.1.1.md`, CHANGELOG `[0.1.1]`, the version bump.
- The unit suite: 1527 passed, 3 skipped (from 1441 at the stage's first commit).

## 10. Confidence / risk

- **High confidence:**
  - the per-case table in §1: two independent read-only reads agree on all 25 cases, at three
    different times;
  - the per-stack verdict logic (unit-tested on every status combination);
  - the CI measurement change: `vv-smoke` on #73 ran exactly the four active-stack tests, and the
    SU2 dispatch failed loudly with the real error.
- **Medium confidence:**
  - the SU2 cause: the error names the missing `sm` component and `ompi_info` lists only `vader`,
    but no SU2 solve has been run with `self,vader`;
  - `strict=True` on the flat-plate `xfail` turns CI red the day the case passes. That is
    intended (a stale marker is loud), but it will surprise whoever fixes the physics.
- **Outstanding risks:**
  - the self-hosted queue paces every PR (45–60 minutes per CI cycle);
  - the release PR's FULL `vv-required` is the first FULL run under the new selection;
  - the tag and any GitHub Release are the operator's.
