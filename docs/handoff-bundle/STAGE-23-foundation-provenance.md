# STAGE 23 — Foundation II: Provenance You Can Trust (ADR-051)

> **Stage 22 closed the first foundation stage** (`v0.1.1`, ADR-051 D4): `aero vv report --latest`
> now reads every registered case's newest run on its own solver stack (no window), the status is
> typed, the verdict is per solver stack (D2 (b)), and no V&V workflow is green when it measured
> nothing. Read its handoff first:
> `docs/handoffs/STAGE-22-foundation-honest-vv-report-DONE-2026-10-16.md`.
>
> **This stage makes the four-tuple mean what CONSTITUTION Invariant 3 says** before Stage 24 runs
> the whole registry under it. Running the registry first would record a whole campaign under the
> weak semantics (ADR-051 D1).
>
> **Verification-scale compute only** (ADR-051 D3): the ADR-050 hosted run, and at most a handful
> of single cluster solves to prove the new terms end to end. No campaign. A tolerance is a
> contract. Stage 20 stays closed. Flexible flapping stays deferred (ADR-046 S4/S5).

## BEFORE YOU START — READ

1. `CLAUDE.md` and `.aero-stage` (set it to `23` in the first commit, with the Dependabot prefix
   `ci(stage-23)`; `tests/unit/test_workflow_hygiene.py` requires the two to agree).
2. The Stage-22 handoff, §2 (decisions), §6 (gotchas) and §7 (open items).
3. **ADR-051** (the charter, row 23 and D1/D3), **ADR-004** (the four-fold provenance contract),
   **ADR-049** (O-07, O-08, H-33), **ADR-050** (the hosted reproducibility case, *proposed*),
   **ADR-047** (result crates, format v1 frozen) and CONSTITUTION Invariant 3.
4. The code under change:
   - `aero/provenance/four_fold.py`: `dvc_input_hash` (the sha256 of the whole repository's
     `dvc status -c` against the configured remote, not of the inputs a case touches; O-07) and
     `container_sif_sha256` (a basename lookup in `containers/SHA256SUMS`, never a re-hash at
     launch; O-08, H-33); `compute_provenance`;
   - `aero/provenance/mlflow.py` (the tags), `aero/crate/` (every crate states both weaknesses).

## Why this stage

Every result the platform reports carries the four-tuple
`(git_sha, dvc_input_hash, container_sif_sha256, config_hash)`. Two of its terms do not mean what
Invariant 3 says:

- **`dvc_input_hash`** is a digest of the repository-wide DVC sync state. Invariant 3 defines it
  over the DVC-tracked inputs *the case touches*. Stage 22 found the inputs are spread over several
  remotes: DrivAerML lives on `aero-nfs` (ADR-011), the small assets on the default `aero-minio`,
  and a bare `dvc pull` can never succeed in this repository. A per-case content address has to be
  defined per input, across remotes, and must not depend on which remote a machine can reach.
- **`container_sif_sha256`** is looked up by file name. Nothing proves the SIF that ran is the one
  whose digest was recorded.

Both weaknesses are stated in every committed crate. Fixing them changes four-tuple semantics, so
each change has its own ADR, and nothing already recorded is relabelled.

## Decisions to put to the operator at stage open (not yet decided)

| # | Question | Notes |
|---|---|---|
| D1 | How does a case declare the DVC inputs it touches? | e.g. an explicit, typed field on the case, checked against what the solver reads; or derived from the paths the case spec names. Fail-loud either way: an undeclared read must be detectable |
| D2 | What exactly does the new `dvc_input_hash` hash? | e.g. the sorted `(path, md5)` pairs from the declared `.dvc` pointers, so it needs no remote; the canonical empty set for a case with none (ADR-050 D3) |
| D3 | How is the SIF re-hashed at launch, and where? | on the solve host, before the solve, compared against `containers/SHA256SUMS`; a multi-GB SIF costs seconds per launch, so any caching must be keyed so that a changed file can never reuse a stale digest |
| D4 | How are runs recorded under the old semantics told apart? | never relabel: a new tag or a semantics version on the tuple; crates keep stating the old limitation for the old runs (format v1 is frozen; a new field is v2 plus an ADR) |
| D5 | ADR-050 (proposed): accept it as written, amend it, or defer it | it is ADR-051's end-to-end proof for this stage, and it adds a claim scope to crate format v1 |
| D6 | The 23 ↔ 24 reorder clause of ADR-051 D1 | only if the provenance work blocks |

## Deliverables

1. **Bookkeeping (first commit):** `.aero-stage` → `23`; the Dependabot prefix → `ci(stage-23)`;
   a `status: partial` handoff `docs/handoffs/STAGE-23-foundation-provenance-DONE-YYYY-MM-DD.md`
   with `stage_tag: v0.1.2` (ADR-051 D4), `next_stage: 24` and
   `next_stage_name: "Stage 24 — Foundation III: Run the Registry"`; regenerate the README.
2. **O-07, a content-addressed `dvc_input_hash`:** its ADR (D1, D2, D4), the implementation, and
   tests (a case with no DVC inputs; a case whose input changes; an undeclared input is refused).
3. **O-08, the SIF re-hashed at launch:** its ADR (D3), the implementation on the solve path, and
   tests with a fake executor (a matching SIF passes; a swapped SIF of the same name is refused).
4. **The end-to-end proof:** ADR-050's hosted, CPU-only `blasius_flat_plate` run emitting one
   number, its four-tuple and a result crate (if D5 accepts it), plus one cluster solve under the
   new terms whose MLflow tags are read back and checked.
5. **The lock refresh for the pip-audit advisories** (161 across 20 packages on 2026-10-12): a
   `uv.lock` refresh, the licence `refresh` (`ci/licence/metadata-snapshot.json`, and possibly a
   reviewed exact-version exception), re-verification, and **one FULL `vv-required` run**.
6. **The close: `v0.1.2`** by the ADR-049 R3 release PR, as Stage 22 did for `v0.1.1`. The operator
   cuts the tag after `release_readiness.py --gate release --online` prints `READY TO TAG v0.1.2`.

Ride-alongs only if 1–6 are done: H-34 (path-safe preCICE directory fields) and H-35 (3MF zip
caps), each a FULL `vv-required` run (ADR-049 P2; ledger).

## GO / NO-GO

- **GO requires:** deliverables 1–6 (the tag itself is the operator's); each semantics change has
  an accepted ADR; no recorded run or committed crate is relabelled; all required CI green.
- **NO-GO** leaves the handoff `partial` and names what is missing. "Not yet" is an acceptable
  outcome; a provenance term that silently means something else is not.

## Infra, conventions and inherited notes (from Stage 22)

- **The production gate:** `aero vv report --latest`; its verdict is per solver stack (ADR-051 D2).
  It is RED on the OpenFOAM stack today (4 fail, 9 missing), so no run may be tagged `production`.
  `scripts/vv_report_crosscheck.py` is the independent full-pagination read.
- **CI and merging:**
  - 12 required contexts (`.github/required-checks.json`); strict protection, one merge per main
    movement; the agent may merge once all 12 are green and announces each merge.
  - Squash merges break stacked branches: merge `main` into the next branch, and **reword the merge
    commit to a Conventional Commit before pushing** (commit-lint checks every commit in a PR).
  - Check every header is ≤ 100 characters **before** pushing:
    `git log --format=%s origin/main..HEAD | awk 'length>100'`.
  - Never push while a self-hosted job on that branch is in progress, and never cancel one. A PR's
    `vv-smoke` keeps running after the PR merges and holds a runner for ~30 minutes, so pace merges.
  - `aero/vv/**`, `aero/adapters/**`, `aero/geometry/**`, `conf/case/**` and `pyproject.toml`
    trigger a FULL `vv-required` run (30–40 min). `aero/provenance/**` does not, but a provenance
    change reaches every solve, so run one FULL cycle before the close regardless.
  - The informational pip-audit check fails until deliverable 5 lands.
- **V&V CI since Stage 22:** `AERO_VV_REQUIRE_CLUSTER=1` (a not-ready cluster fails); `xfail` only
  on `AssertionError`; `su2` and `unmeasurable` markers; `vv-transonic` is dispatch-only; every V&V
  job writes a step summary (`scripts/vv_ci_summary.py`).
- **MLflow** is on `aero-mlflow:5000`. Read it with the `provenance` extra; never write to it from a
  test (`tests/unit/_fake_mlflow.py` is the fake client).
- **Long jobs** go through `scripts/run_long.sh` with REAP on. Never use `run_long.sh wait`.
- **Hard don'ts** (unchanged): never create the two ADR-045 records; never fill a B-sentinel; keep
  `stage-20-evidence-2026-09-20`; never write a crate under `data/vv/`.
- **Release tags:** the agent's `git tag` is refused by the auto-mode classifier; the operator cuts
  them. `release_readiness.py` requires the v0.1.0 limitation sentence verbatim in every
  release's notes ("... and v0.1.0 makes no flapping-wing optimization claim."); the v0.1.1
  notes carry it (still true) and add that v0.1.1 makes none either. Keep that pattern, or
  generalise the check in its own reviewed change before the bump commit.
- **PR #21** (repointing the `aero-nas` DVC remote to `.60`) is unrelated to CI, which uses
  `aero-minio`. It stays "leave unless the operator asks", but it bears on D2 if a case's inputs
  live on `aero-nas`.

## POST-STAGE HANDOFF (mandatory)

One file, kept from the first commit to the close. Emphasise:
- the old and new definition of each changed term, and how a reader tells them apart (D4);
- the operator's answers to D1–D6;
- the end-to-end proof: the hosted run's number and crate digest, and the cluster run's tags;
- anything Stage 24 (running the registry) must know, including its compute plan's inputs.

Author the Stage-24 prompt (`docs/handoff-bundle/STAGE-24-foundation-run-the-registry.md`) before
closing.
