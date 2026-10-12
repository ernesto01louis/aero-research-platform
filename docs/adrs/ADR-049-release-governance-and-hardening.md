# ADR-049 — Release governance and the Stage-21 hardening scope: the release-tag gate, verifiable "all required CI green", CI supply chain, and the closed hardening list

- **Status:** accepted. Proposed 2026-10-12, and ratified by the merge of the Stage-21 constitution
  PR. That merge followed the ≥72 h window and the operator's sign-off recorded in the PR
  (CONSTITUTION "Amendment process"; the ADR-027 two-track precedent).
  CLAUDE.md Hard Rule 10 is extended to `vX.Y.Z` release tags, and the stale constitutional text is corrected.
- **Date:** 2026-10-12
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 21)
- **Stage:** 21
- **Supersedes:** none

## Context and problem statement

ADR-046 S1 makes "hardening" a Stage-21 deliverable without bounding it. The stage-open audit
(2026-10-11) found broken release machinery and security exposure that would ship with v0.1.0.

**Release gating**
- **The release tag is ungated.** `tag-handoff-gate.yml` triggers only on `v0.0.*`, and its parser
  (`${tag##v0.0.}`) cannot read `v0.1.0`. Even for `v0.0.*` tags, the validator
  (`scripts/check_handoff_exists.sh`) checks five frontmatter fields on the newest-mtime handoff.
  It never compares `stage_tag` with the tag, never requires `status: complete`, and never checks
  that `git_sha_end` exists.
- **"All required CI green" is a convention, not a block.** `enforce_admins` is false; the sole code
  owner is the PR author; PR #45 merged with a red required check.

**CI supply chain and security**
- **Mutable actions and runners.** All 38 action references are mutable tags, including the
  third-party `dorny/paths-filter@v3` inside the secret-bearing `vv-required` job. `ubuntu-latest`
  moves to Ubuntu 26 from 2026-10-19, and the Node-20 runtime has already been removed from runners.
- **Fork PRs reach self-hosted runners.** On this public repo, three self-hosted jobs can be
  triggered by a fork pull request (`vv-required`, `vv-smoke`, `provenance-completeness`). Approval
  is required only for first-time contributors, and fork runs get no secrets, so `vv-required`
  passes vacuously.
- **Shell injection.** `commit-lint` splices the PR title into bash; `moving-vv` splices a dispatch
  input into bash on a self-hosted runner.
- **Unbounded self-hosted jobs.** `vv-transonic` has no concurrency group and no
  `AERO_RUN_LONG_REAP`, although its SU2 path uses `run_long.sh`.

**Workflows that report nothing real**
- `license-audit` scans zero files.
- `vv-scale-resolving` is a no-op that reports green.
- `moving-vv` has been red for five weekly runs (`plunging_airfoil_hg2007`, rc=124 at the 4 h
  ceiling).

**Packaging and install**
- No workflow builds or installs the wheel, and CI ignores `uv.lock`.
- The version is not single-sourced: pyproject says `0.0.1`, CITATION says `0.0.4`, and the
  required test `tests/unit/test_smoke.py` pins `^0.0.1`.
- `pip install aero` installs an unrelated 2011 PyPI package.

**Schema and dependency holes**
- **FAIL-LOUD holes in a constitutional gate.** Non-finite floats are accepted in the
  `ReportableResult` tree, and a NaN delta passes `SmallSignalError` (`reportable.py:413`).
- **Libm-dependent U95 arithmetic.** The RSS uses `**2` and `math.hypot`, which differ from
  `x*x` and `sqrt(a*a+b*b)` in the last bit on some inputs. A cross-OS bit-exact round trip cannot
  rest on them.
- **Import isolation.** `aero.vv.reportable` cannot be imported without loguru.

**Provenance and documentation**
- **Provenance SHAs are not public.** Stage 17's SHAs are unpushed; Stages 12/15/16 survive only on
  deletable branches.
- **Documentation drifted** from reality: SECURITY.md, CONTRIBUTING.md, the PR template, two
  `.claude/rules` files, the CHANGELOG, the deferred-work ledger, and several CONSTITUTION
  sentences.

## Decision drivers

- v0.1.0 is the platform's first release for outside readers and JOSS reviewers.
- Hardening is **machinery and honesty, not features**: SCOPE-GATE, and no compute in Stage 21.
- Every change is test-pinned. Every new required context must have gone green on main once before
  it is required.
- Claude's own hook and permission configuration, repo settings, tags and Releases stay with the
  operator.

## Decision outcome

### R1 — The release-tag gate (Hard Rule 10 extended to release tags)

- **A new wrapper, `scripts/check_release_tag.sh <tag> [--ci|--pre-tag]`.**
  `scripts/check_handoff_exists.sh` is NOT edited: it is the Stop hook, and its behaviour for
  partial handoffs must not change.
  - **For `v0.0.N`:** the legacy path, unchanged.
  - **For `vX.Y.Z`:**
    - exactly one `docs/handoffs/STAGE-*-DONE-*.md` carries `stage_tag: <tag>`;
    - the five-field validator passes for that stage;
    - `status: complete`;
    - `git_sha_end` resolves as a commit;
    - its code tree equals the tagged tree. Ancestry cannot be checked under squash merges.
    - `next_stage` is set and its prompt file exists;
    - the pyproject version, the CITATION `version` and a CHANGELOG `## [X.Y.Z]` heading agree with
      the tag.
- **`tag-handoff-gate.yml`** triggers on `v*.*.*` with full history. Evidence tags (`stage-NN-evidence-*`)
  never match.
- **Hard Rule 10's wording becomes:** "No `v0.0.NN` stage tag or `vX.Y.Z` release tag without the
  matching post-stage handoff with valid frontmatter". Ratified in the micro-PR.

### R2 — Verifiable release readiness

`scripts/release_readiness.py` (stdlib) refuses a release unless:
- every registered required context is `success` on the release commit, and skipped, neutral,
  cancelled or missing counts as not green;
- versions agree;
- the limitation is in the **body** of the release notes and the paper;
- no operator sentinel remains in the release metadata;
- the licence scan passes;
- every cited surrogate certificate has more than 30 days of validity left;
- every crate's git SHA resolves on GitHub;
- the hard don'ts hold:
  - both ADR-045 records are absent;
  - `stage-20-evidence-2026-09-20` exists on origin;
  - the B-sentinel counts are unchanged.

`.github/required-checks.json` registers the required contexts. A hygiene test keeps every
registered context byte-identical to exactly one job name.

### R3 — Release sequence

Stage 21's stage tag **is** `v0.1.0`; there is no `v0.0.21`.

The release PR:
- bumps the static version to 0.1.0 (pyproject, `uv.lock`, CITATION, CHANGELOG);
- completes the Stage-21 handoff;
- authors the Stage-22 prompt.

Then:
1. The operator tags v0.1.0 at the commit the readiness check names.
2. `tag-handoff-gate` must go green.
3. The first PR after the tag regenerates the README STATUS block. The tag must exist first, so the
   tagged tree reads "(not yet tagged)" by design.
4. The operator publishes the GitHub Release: published, not a draft or pre-release. That mints the
   Zenodo version DOI.

Distribution is the GitHub Release (wheel, sdist, crate zips, licence report, `SHA256SUMS`) plus
Zenodo. **No PyPI at v0.1.0**: the name `aero` is taken and the jaxfluids git reference blocks
upload. A distribution-name ADR is ledgered. There are no backfilled Releases for v0.0.8–v0.0.20 and
no backfilled v0.0.5 tag, because each would mint a stale-metadata DOI.

### R4 — The closed hardening list

Anything newly found during the stage goes to `docs/operator/deferred-work-ledger.md` under
"Stage 21", unless it blocks GO.

**IN — P0 (release-blocking)**

| ID | Item |
|---|---|
| H-01 | Release-tag gate (R1) |
| H-02 | Non-finite floats refused in the reportable / paired / statistical models. The NaN-safe small-signal guard is `if not (delta > required_margin)`. `crosscheck_ratio = inf` stays legal and serialises as `"Infinity"`. |
| H-03 | IEEE-exact RSS: `x*x` and `sqrt(a*a + b*b)` replace `**2` and `math.hypot`. Every committed U95 value reproduces bit-identically. |
| H-04 | Version single-sourced and tested: pyproject = `aero.__version__` = `uv.lock` root, and CITATION at the bump. The silent fallback becomes `"0+unknown"`. |
| H-05 | Truthful install text (no `pip install aero`) |
| H-06 | Release readiness (R2) |
| H-07 | Annotated evidence tags for the Stage 12/15/16/17 provenance SHAs, after a gitleaks scan (operator decision D4) |
| H-08 | CI supply chain: SHA-pinned actions at current majors; `runs-on: ubuntu-24.04`; top-level `permissions`; step-scoped secrets; pinned uv; `persist-credentials: false`. **Before 2026-10-19.** |
| H-09 | Shell injection in commit-lint and moving-vv: values go through `env`, and are validated |
| H-10 | `vv-transonic`: `AERO_RUN_LONG_REAP` first, then a non-cancelling concurrency group |
| H-11 | Fork-PR exposure: same-repo guards on the non-required self-hosted PR jobs. The primary control is the operator setting "require approval for all external contributors". Splitting `vv-required` into a hosted decide job, a same-repo cluster job and a hosted aggregator with the unchanged context name is optional and **propose-first**. |
| H-12 | Import isolation: lazy loguru in `aero/adapters/_base.py` and `aero/orchestration/local_ssh.py`, plus a blocked-import subprocess test |

**IN — P1**

| ID | Item |
|---|---|
| H-13 | Structural `extra='forbid'` test over all aero models |
| H-14 | Wheel built from the sdist and installed on clean runners (crate round-trip) |
| H-15 | Locked installs in CI; `uv lock --check` |
| H-16 | `Path(__file__).parents[N]` repo-root lookups fail loudly outside a source checkout |
| H-17 | Hosted, non-required run of `tests/stage_*` with a triage table (time-boxed) |
| H-18 | A real certificate-watermark check in `license-audit` |
| H-19 | `vv-scale-resolving` loses its schedule and fails loudly |
| H-20 | `moving-vv` recorded as known-failing; read-only triage only (a compute fix is OUT) |
| H-21 | Dependabot for github-actions, with the stage-scoped commit prefix |
| H-22 | gitleaks in CI (non-required) |
| H-23 | pip-audit (non-required) |
| H-24 | CITATION validated by cffconvert in the required unit job |
| H-25 | Docs match reality: SECURITY, CONTRIBUTING, the PR template, the two `.claude/rules` files, CLAUDE.md stale notes, 00-MISSION/output-validity-bar "Stage 20" |
| H-26 | CHANGELOG `[Unreleased]`, link refs, a dated correction under `[0.0.20]` (the entry is not rewritten), and the missing Invariant-12 / Invariant-3 entries |
| H-27 | Refresh the deferred-work ledger: close the two items already fixed in `bc1384a`, add Stage 20/21 |
| H-28 | Remove the now-dead `0b6d774` commit-lint exemption |
| H-29 | ADR-046 typos: the "(proposed)" heading and the wrong precedent commit, as a dated note. The decision text is untouched. |
| H-30 | CODE_OF_CONDUCT, issue templates (the bug report requires the four-tuple or a crate id), and a support section |
| H-31 | The handoff template's inline comments, which broke the Stop-hook parser (fixed in PR-01) |
| H-32 | Required-check registry and workflow hygiene test |
| H-33 | Provenance weaknesses documented: `dvc_input_hash` is sync-state; the SIF digest is a basename lookup |

**IN — P2** (only if ready alongside P0/P1, otherwise ledgered)

| ID | Item |
|---|---|
| H-34 | Path-safe patterns on preCICE directory fields, plus `shlex.quote` |
| H-35 | 3MF zip caps |
| H-36 | Drop the non-existent `nvidia-physicsnemo[cu12]` extra name |

**OUT** (ledgered with destination)

| ID | Item | Reason |
|---|---|---|
| O-01 | Stage-11 PSS S3/S5 backfill | needs re-runs |
| O-02 | Mesh fallback ladder / checkMesh gate in the V&V runner | behaviour change, needs cluster verification |
| O-03 | Bowtie vertex check | new quality gate |
| O-04 | 3-D external geometry | feature |
| O-05 | Fair-test speed-up | new campaign |
| O-06 | The 393² rung | 10–14 days of compute |
| O-07 | Content-addressed `dvc_input_hash` | changes four-tuple semantics; post-v0.1.0 ADR |
| O-08 | Re-hashing the SIF at launch | cluster code path |
| O-09 | RunPod `StrictHostKeyChecking=no` | frozen GPU path |
| O-10 | Claude hook changes | operator-only |
| O-11 | PyPI | — |
| O-12 | A docs site | — |
| O-13 | Release backfills | — |
| O-14 | Container licence scan / SBOM | — |
| O-15 | A full Python 3.13 test leg | — |
| O-16 | A moving-vv compute fix | — |
| O-17 | `enforce_admins` | deadlocks with a sole code owner; R2 substitutes |
| O-18 | Platform markers on the jax-fluids NVIDIA wheels | — |
| O-19 | actionlint / zizmor | — |
| O-20 | A coverage threshold | — |
| O-21 | Stage-13 crates | schema drift; refused |
| O-22 | Crates for Stages 18–20 | — |
| O-23 | Re-certifying the Stage-17 surrogate | compute |
| O-24 | Ephemeral runners, CodeQL, tag rulesets | operator settings |

### R5 — JOSS boundaries

Stage 21 ends at "ready to submit". The repo must be public for more than six months, so submission
is on or after 2026-11-18, and it is the operator's act. Every reply to JOSS editors or reviewers is
written by the operator, because JOSS forbids AI for author–editor and author–reviewer conversation.
The paper's AI-usage disclosure is generated from the handoff frontmatter and the commit trailers.
The human-review statement in it is the operator's own.

### Consequences

- **Positive:**
  - The release is gated by machinery that checks what it claims.
  - Outside contributors cannot reach the cluster through a fork PR unseen.
  - The scope is closed, so hardening cannot sprawl.
- **Negative:**
  - Two more required contexts.
  - A hygiene test that fails on careless workflow edits.
  - One extra FULL vv run at the release PR.
- **Follow-up:** the OUT list, plus the operator settings (fork approval, CodeQL, tag ruleset, the
  Stop-hook path via `$CLAUDE_PROJECT_DIR`).

## Links

- ADR-046 S1; CLAUDE.md Hard Rules 5, 9, 10; CONSTITUTION Invariants 1, 3, 5, 6, 9; ADR-047, ADR-048.
- GitHub, "Security hardening for GitHub Actions" (SHA pinning; self-hosted runners on public repos).
- JOSS submission requirements and AI usage policy (https://joss.readthedocs.io/en/latest/submitting.html).
