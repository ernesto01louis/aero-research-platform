# STAGE 22 — Foundation I: An Honest V&V Report (ADR-051)

> **v0.1.0 is released and Stage 21 is CLOSED.** Tag `v0.1.0` → `9d02892`; Zenodo version DOI
> 10.5281/zenodo.23396402. The JOSS submission is deferred until the platform has evidence of
> research use (`docs/release/joss.md`).
>
> **ADR-051 puts the foundation first.** Stages 22–26 build an honest, validated base before any
> new optimization. This stage is the first of the five: **make the production gate show the
> truth.** Rigid-flapping optimization comes after Stage 26
> (`docs/handoff-bundle/LATER-rigid-flapping-optimization.md`).
>
> **No campaign compute in this stage.** This is code, tests, CI and decisions. Running the registry
> is Stage 24, under Stage 23's provenance, with its own approved compute plan.
>
> **A tolerance is a contract.** Never relax one, and never mark a case `pass` that has not passed.
> Stage 20 stays closed (never retry a lever or fill a B-sentinel). Flexible flapping stays
> deferred (ADR-046 S4/S5).

## BEFORE YOU START — READ

1. `CLAUDE.md`, and `.aero-stage` (set it to `22` in the first commit).
2. `docs/handoffs/STAGE-21-release-portable-bundles-DONE-2026-10-12.md` §6 (gotchas) and §7.
3. **ADR-051** (this stage's charter), **ADR-005** (the V&V harness and the "red dashboard = no
   production" rule), ADR-013 (frozen-optional solvers), ADR-046 S4 (deferred flexible flapping).
4. The code under repair:
   - `aero/cli.py`, `vv_report` (around lines 806–900): it reads `search_runs(...,
     max_results=500)` at `:858`;
   - `aero/vv/dashboard.py`: `DashboardEntry.status` is a free `str`;
   - the registries that `vv_report` unions (`aero/vv/{tmr,forward_regime,ercoftac,unsteady,
     flapping,transonic,scale_resolving,external_geometry,fsi}/__init__.py`).
5. The V&V workflows: `vv-smoke.yml`, `vv-transonic.yml`, `vv-required.yml`, `moving-vv.yml`,
   `vv-scale-resolving.yml`.
6. `docs/vv/output-validity-bar.md`.

## Why this stage

`aero vv report --latest` is the gate for every `production`-tagged run (ADR-005). At Stage 21's
close it printed 5 pass, 1 fail, 20 missing. The truth, read by paging the whole MLflow experiment
(2388 runs), was **7 pass, 4 fail, 14 no run**:
- **The report reads only the 500 newest runs.** `vv-smoke` logs four smoke cases per push, 1405
  runs in all, and they push every older V&V run out of the window.
- **Hidden by the window:** three failures (`naca0012_verification`, `plunging_airfoil_hg2007_st03`,
  `_st03_lm`) and three passes (`t3a_flat_plate_transition`, `turek_hron_cfd2`, `turek_hron_cfd3`).
  All six showed as "missing".
- **The nightly `vv-transonic` job is green while measuring nothing.**
  - ONERA M6 was SKIPPED after "solver failed (rc=1)", because `dvc pull` printed "skipped" and the
    DVC-tracked mesh was never fetched.
  - The transonic NACA 0012 test is XFAIL.

The full table is in ADR-051 §1. The RED verdict was right; the information behind it was not. A
foundation cannot be built on a gate that misreports.

## Operator decisions at stage open (ask before building on them)

| # | Decision | Recommended |
|---|---|---|
| D2 | What happens to the 5 cases that cannot run on the active stack: the SU2 transonic pair and the PyFR GPU pair (frozen-optional, ADR-013), and `hg2007_flexible_foil` (deferred, ADR-046 S4) | **(b) Scope the verdict per solver stack.** Frozen and deferred cases stay registered and visible with a typed status, never `pass`, and no longer gate a stack they do not measure. Option (a) runs them; option (c), removing them, is rejected (ADR-051) |
| D4 | The stage tag after v0.1.0 | **`v0.1.1`**: a patch version per foundation stage, via the ADR-049 release PR and tag gate. A GitHub Release (Zenodo DOI) only when the operator chooses |

Record both in the handoff, and in an ADR if D2's answer changes ADR-005's rule.

## Deliverables

### 1. Bookkeeping (first commit)

- `.aero-stage` → `22`, and the Dependabot commit prefix → `ci(stage-22)` (the workflow-hygiene
  test enforces that the two agree).
- A `status: partial` Stage-22 handoff from the first commit on, with `stage_tag` per D4,
  `next_stage: 23` and `next_stage_name: "Stage 23 — Foundation II: Provenance You Can Trust"`.
  Regenerate the README in the same commit.

### 2. The report reads the truth

- Replace the 500-run window with a per-case query. For each registered case, ask MLflow for its
  newest run: `filter_string="tags.validation_tag = '<case>'"`, newest first, one result.
  Unregistered tags (the `-sweep` runs, and the tier-named tags `thesis-grade` and `validated` found
  in the experiment) never enter the verdict.
- The non-`--latest` listing pages explicitly, or states its bound in its output. It never
  truncates silently.
- **Tests,** with a fake MLflow client (no cluster in CI):
  - a run older than any window is found;
  - a case with zero runs is `missing`;
  - a failing case hidden behind newer runs of other cases is still `fail`;
  - a run with no `vv_status` is `unknown`, never `pass`.

### 3. Typed status and the verdict

- `DashboardEntry.status` becomes a `Literal`. Its values are `pass`, `fail`, `regress`,
  `missing`, `unknown`, plus `frozen` and `deferred` if D2 is (b). An unknown string fails loudly.
- **The verdict follows D2.** Under (b), each solver stack's verdict is green only if every case on
  that stack is `pass`. `frozen` and `deferred` render distinctly and never count as `pass`.
- The report says which stack a production run would be gated by. Update the ADR-005 rule's wording
  in CLAUDE.md to match, citing the decision's ADR.

### 4. No V&V workflow is green when it measured nothing

Audit `vv-smoke`, `vv-transonic`, `moving-vv`, `vv-required` and `vv-scale-resolving`:
- **A solver failure is a failure, not a skip.** Start with ONERA M6: find out why `dvc pull` falls
  through to "skipped" on the self-hosted runner. Then either fetch the mesh, or fail loudly when it
  is missing.
- **A skip is allowed only for a resource absent by design** (for example, no GPU runner). The job
  summary must then say so in words, and the case must never be logged or counted as a V&V pass.
- **Record a table** in the handoff: each workflow, what it measured in its last run, and what
  changed.
- **Open PR #21** (repointing the `aero-nas` DVC remote to the hardware NAS) may bear on the
  `dvc pull` failure. It stays "leave unless the operator asks", so raise it with the operator; do
  not touch it.

### 5. The per-case table

Run the fixed `aero vv report --latest` and record its full output in the handoff, with MLflow run
ids. Cross-check it against an independent read: a full pagination of the experiment by a small
read-only script under `scripts/`. The two must agree case for case.

### Ride-alongs, only if 1–5 are done (otherwise they stay ledgered)

- A unit test for `scripts/regenerate_status.sh` (ledger, Stage 21).
- H-34, path-safe preCICE directory fields; and H-35, 3MF zip caps (ADR-049 P2).

## GO / NO-GO

- **GO requires all of these:**
  - deliverables 1–5;
  - the fixed report agrees case for case with the independent full-pagination read;
  - no V&V workflow reports green on a run that measured nothing;
  - D2 and D4 decided and recorded;
  - all required CI green.
- **NO-GO** means the handoff stays `partial` and names what is missing. This stage changes what the
  report *shows*, never what a case *is*: no case moves to `pass` without a passing run.

## Infra, conventions and inherited notes

- **CI and merging:**
  - There are 12 required contexts, listed in `.github/required-checks.json`.
  - Protection is strict, so there is one merge per main movement.
  - Squash merges break stacked branches: merge `main` into the next branch and take main's copy of
    the files the base introduced.
  - Never push while a self-hosted job on that branch is in progress, and never cancel one.
  - Check that every commit header is ≤ 100 characters **before** pushing.
  - `aero/cli.py` is outside the `vv-required` paths filter; `aero/vv/**` is inside it, so a change
    there is a FULL run.
- **MLflow** is on `aero-mlflow:5000`. Read it with the `provenance` extra; never write to it from a
  test.
- **The V&V report is RED today.** No run may be tagged `production`.
- **Long jobs** go through `scripts/run_long.sh`, with REAP on. Never use `run_long.sh wait`.
- **Hard don'ts** (unchanged):
  - never create the two ADR-045 records;
  - never fill a B-sentinel;
  - keep `stage-20-evidence-2026-09-20`;
  - never write a crate under `data/vv/`.
- **Release tags:** the agent's `git tag` is refused by the auto-mode classifier. The operator cuts
  release tags.

## POST-STAGE HANDOFF (mandatory)

One file, kept from the first commit to the close. Emphasise:
- the per-case table (before and after the fix), with run ids;
- the D2 and D4 decisions;
- the workflow audit table;
- anything found that Stage 23 (provenance) or Stage 24 (running the registry) must know.

Author the Stage-23 prompt (`docs/handoff-bundle/STAGE-23-foundation-provenance.md`) before closing.
