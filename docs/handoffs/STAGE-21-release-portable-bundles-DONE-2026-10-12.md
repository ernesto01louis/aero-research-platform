---
stage: 21
stage_name: "Stage 21 — Release: Portable Bundles + Hardening + v0.1.0"
status: partial
date_started: 2026-10-11
date_completed: 2026-10-12
session_duration_hours: 14
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-5-5
git_sha_start: 83baa43225cd9a5f9684a0481b8502b6004fa49c
git_sha_end: 83baa43225cd9a5f9684a0481b8502b6004fa49c
stage_tag: v0.1.0
next_stage: 22
next_stage_name: "Stage 22 — Rigid-Flapping Optimization"
---

# Stage 21 — Release: Portable Bundles + Hardening + v0.1.0 — IN PROGRESS (partial)

> **Stage 21 is OPEN and `partial`.** All build work is up as PRs **#47–#58**, and all of them
> are green except informational jobs. **Nothing is merged yet:** the auto-mode classifier refuses
> agent merges ("Merge Without Review"), so merging is the operator's. `git_sha_end` stays at the
> stage-open main commit until something merges.
>
> - **Do not create a second Stage-21 handoff.** The Stop hook picks the newest-mtime file and the
>   README generator the lexicographically last.
> - **The prompt of record** is `docs/handoff-bundle/STAGE-21-release-portable-bundles.md`. Its
>   operator-decision table (D1–D4) and its record-faithful wording table bind this stage.
> - **The plan of record** is `docs/adrs/ADR-047` / `048` / `049` (#48).

## 1. Deliverables status

| # | Deliverable (verbatim from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | Bookkeeping (PR-01) | ✅ | **#47**: `.aero-stage` 21, prompt of record, Hard Rule 16 → Stage 21, template comments moved to their own lines, this handoff |
| 2 | Result crates — the RESULTS-MUST-TRAVEL bundle (ADR-047) | ✅ (in review) | **#50** core hardening (prerequisite). **#51** `aero/crate/` format v1, plus an RO-Crate 1.3 conformance fix. **#53** the five committed crates under `crates/`, an independent oracle, `test_crate_committed` |
| 3 | Round-trip CI (`crate-roundtrip.yml`) | ✅ (in review) | **#52**: clean Linux 3.12/3.13, macOS, Windows and floor read legs. **#53** adds the committed crates (pinned digests plus the oracle) and a Windows `core.autocrlf=true` checkout leg. All legs green; the external roc-validator now passes too |
| 4 | Dependency licence scan (ADR-048) | ✅ (in review) | **#54**: `scripts/licence_scan.py`, `ci/licence/`, required job `dependency licence scan — Invariant 5`. 302 packages: 291 allowed, 9 identified, 2 admitted, 0 fail. Also the license-audit watermark repair |
| 5 | Hardening — a closed list | ⚠️ | Done: H-01..H-36 except those listed under Deviations. **#49** CI supply chain (before 2026-10-19). **#50** finite U95, IEEE-exact RSS, lazy loguru, version single-source, repo-root, extra=forbid. **#55** release-tag gate plus readiness. **#56** docs truth |
| 6 | JOSS + Zenodo — ends at "ready to submit" | ⚠️ | **#58**: paper (1338 words), bib (20 verified DOIs), generated AI disclosure, `.zenodo.json`, CITATION refresh, release notes, claims ledger. Still needs the operator's metadata (§7) and the 2026-11-18 date |
| 7 | Governance, then v0.1.0 last | ⚠️ | **#57** (DRAFT) is the constitution micro-PR: Invariant 13, Invariant 5 reworded, text fixes, ADR-047/048/049 accepted. It merges no earlier than **2026-10-15**, after both new contexts are required and the operator signs off. **PR-15** (the bump) is not opened yet; it comes last |

**PR map** (base ← head; all squash-merged by the operator):

| PR | Branch | Base | What |
|---|---|---|---|
| #47 | stage-21-open | main | PR-01 bookkeeping |
| #48 | stage-21-adrs | stage-21-open | PR-02 ADR-047/048/049 (proposed) |
| #49 | stage-21-ci-supply-chain | main | PR-03 SHA pins, ubuntu-24.04, locked installs, injection/REAP fixes, registry and hygiene test |
| #50 | stage-21-core-hardening | main | PR-05 FULL vv-required; finite floats, exact RSS, lazy loguru, version |
| #51 | stage-21-crate | #50 | PR-06 `aero/crate/` format v1 |
| #52 | stage-21-crate-ci | #51 | PR-07 crate round-trip CI |
| #53 | stage-21-crates | #52 | PR-08 the five committed crates |
| #54 | stage-21-licence-scan | #49 | PR-09 dependency licence scan |
| #55 | stage-21-release-gate | #49 | PR-10 release-tag gate + readiness |
| #56 | stage-21-docs-truth | #47 | PR-11 docs match reality, community files |
| #57 | stage-21-constitution | #56 (+#48 merged in) | PR-14 constitution micro-PR (**draft**) |
| #58 | stage-21-joss | #53 | PR-13 JOSS / Zenodo / CITATION / release notes / claims ledger |

**Evidence tags** (D4) are on origin, annotated, and pushed after a clean gitleaks scan:
- `stage-12-evidence-2026-07-05` → 33a1b13b;
- `stage-15-evidence-2026-07-12` → c385c01a;
- `stage-16-evidence-2026-07-15` → 152d381a;
- `stage-17-evidence-2026-07-24` → e2463585, which published 37 previously local-only commits.

`stage-20-evidence-2026-09-20` is untouched.

## 2. Decisions made

- **Stage scope** is ADR-046 S1, not re-argued. Operator decisions D1–D4 (2026-10-11):
  - D1: a GPL-3.0-compatible allowlist, scoped; dvc stays in base.
  - D2: record-faithful wording; ADR-046 untouched, except a dated errata note (H-29).
  - D3: crate content licence is CC-BY-4.0.
  - D4: evidence tags.
- **"Result crate", `aero/crate/`, format v1.** It uses:
  - RO-Crate 1.3 + Process Run Crate 0.6 + a PROV-JSON sidecar;
  - content-addressed config preimages (`sha256(file) == config_hash`);
  - `SHA256SUMS`, whose sha256 is the citable crate digest;
  - deterministic ZIP_STORED;
  - a stdlib CLI under an audit-hook sandbox.

  The crate keeps computed fields, under a lossless-subset rule, so recomputation becomes a
  bitwise checksum. Rejected: excluding computed fields, and a lazy `aero.vv` package (that hides
  the import violation).
- **Era recipes are one-shot, in `scripts/stage21_export_crates.py`.** HEAD's CaseSpec gained
  fields after the runs (`section`, `first_cell_*`, the graded default), so each era's payload is
  rebuilt and the recorded `config_hash` asserted. CI **never** re-runs a recipe (`check`), so a
  future field cannot turn CI red.
- **Stage 14 is evidence-only (claim tier `none`).** Its four-tuple was never recorded, so it
  cannot carry a tier.
- **An independent oracle** (`scripts/crate_oracle.py`, stdlib, never imports aero) pins the five
  crate digests. It compares every number the crates carry (139 values) against the committed
  records.
- **The external roc-validator found three RO-Crate 1.3 MUSTs** that the in-repo checks lacked:
  Profile entities, `version` on SoftwareApplication, and the citation typed as a Script. They
  were fixed in the projector **before format v1 freezes**, with the crates re-exported (numbers
  unchanged; only the RO-Crate metadata and SHA256SUMS changed). The fix was merged forward
  through #51 → #52 → #53 with conventional merge commits, so there were no force-pushes.
- **Licence exceptions** are each pinned to the upstream LICENSE at the released tag. Two kinds:
  - `identify`: metadata missing or contradictory;
  - `admit`: grandalf and pygit2, dvc's GPL-2 family.

  The 26 NVIDIA wheels plus `cuda-toolkit` are allowed only in `gpu-frozen`.
- **The release-tag gate is a new wrapper**, `scripts/check_release_tag.sh`. The Stop hook
  (`check_handoff_exists.sh`) is unedited and still validates the five fields. "All required CI
  green" is verified online by `release_readiness.py`: skipped, neutral or cancelled is not green,
  and PR-only contexts are read on the merged PR head with a tree check.
- **PR-14's base** is #56 with #48 merged in, so its CHANGELOG `[Unreleased]` entry and ADR
  status flips do not conflict later. It is a **draft**, to make an early merge impossible.
- **v0.1.0 is Stage 21's stage tag.** There is no `v0.0.21`.

## 3. Deviations from the stage plan

- **Agent merges are refused** by the auto-mode classifier. Every merge, and therefore every
  "after it is green on main" step, is the operator's. This stage therefore ends with a reviewed
  PR stack, not a release.
- **Not done (optional or ledgered):**
  - PR-04, the vv-required restructure (optional, propose-first);
  - PR-12, a hosted run of `tests/stage_*` (optional);
  - a `regenerate_status.sh` unit test (ledgered).
- **H-34 and H-35 (P2) were NOT done.** They are ledgered per ADR-049 R4 (#56):
  - H-34: path-safe patterns on the preCICE directory fields, plus `shlex.quote`;
  - H-35: 3MF zip caps.

  H-36, the `[cu12]` extra name, is done (#50).
- **The licence exceptions' `reviewer` field** says "Claude Code (Stage 21 agent); operator review
  at ADR-048 ratification". The operator reviews them in #54/#57.
- **pip-audit (informational) reports 161 advisories across 20 locked packages.** It is ledgered;
  a lock refresh is its own change, with a FULL vv-required run.

## 4. Environment / dependency / schema changes

- **`pyproject.toml`** (#50):
  - `pydantic>=2.12`;
  - a `stage_21` pytest marker;
  - Development Status 3 - Alpha;
  - the 3.13 classifier and the cut keywords dropped;
  - `nvidia-physicsnemo==1.2.0` without the non-existent `[cu12]` extra.

  `uv.lock` changes only in requires-dist; no package moved.
- **New core package `aero/crate/`** (stdlib + numpy + pydantic). New `aero/_repo.py`.
  `four_fold.canonical_config_bytes`.
- **New committed data** (not under `data/vv/`):
  - `crates/` (five crates + README);
  - `ci/licence/` (policy, exceptions, a 302-package metadata snapshot);
  - `paper/`;
  - `.zenodo.json`;
  - `docs/release/*`.
- **`.gitattributes`** `crates/** -text`, plus pre-commit excludes for `crates/`.

## 5. CI/CD changes

- **New workflows:**
  - `crate-roundtrip.yml`, gate `crate round-trip — Invariant 13`;
  - `dependency-licences.yml`, required job `dependency licence scan — Invariant 5`, plus
    informational re-verify and pip-audit jobs;
  - `secret-scan.yml` (gitleaks, non-required);
  - `release-readiness.yml` (dispatch-only);
  - `joss-draft.yml` (informational);
  - `.github/dependabot.yml`.
- **Changed:**
  - all workflows are SHA-pinned on `ubuntu-24.04`, with `persist-credentials: false` and
    step-scoped secrets;
  - locked installs;
  - commit-lint and moving-vv inputs go through `env`;
  - vv-transonic gets REAP plus concurrency;
  - vv-scale-resolving loses its schedules;
  - fork guards;
  - `tag-handoff-gate.yml` triggers on `v*.*.*`;
  - `license-audit.yml`'s watermark now scans every certificate, and fails on zero.
- **Registry:** `.github/required-checks.json` plus `tests/unit/test_workflow_hygiene.py`.
- **Branch protection is unchanged so far.** The two new contexts are added after their first
  green run on main (operator action).

## 6. Gotchas discovered

- **The handoff template broke the Stop hook.** Inline `# …` comments became part of the
  frontmatter values. Fixed in #47.
- **No committed ReportableResult reloaded into its own model.** Its computed fields clash with
  `extra='forbid'`. The legacy import in `aero/crate/payload.py` strips them type-directed.
- **pydantic `ser_json_inf_nan` applies from the OUTERMOST model.** A legal nested
  `crosscheck_ratio=inf` serialized as `null` until the outer models got `"strings"` (#50).
- **`sum()` uses Neumaier compensation in Python ≥ 3.12.** Exact RSS needs an explicit
  left-to-right `x*x` loop.
- **Retargeting a PR fires only `edited`,** so the CI does not run. Close and reopen it.
- **Stacked PRs only run unfiltered workflows.** pytest, ruff and mypy run once a PR targets main.
  Every branch was checked locally.
- **Squash merges break ancestry.** After a base PR squash-merges, merging `main` into a stacked
  branch conflicts on every file the base introduced. #50 and #49, for example, carry #47's
  commit. Resolve by taking `main`'s version of those files, because the squashed copy is the
  newer one. Then re-run the suite.
- **The ruff-format pre-commit hook can roll back a commit.** Re-add and commit normally, and run
  `git log -1` after every commit.
- **`crates/README.md` sits next to the crate dirs.** Verify with `crates/stage*`, not
  `crates/*`.
- **pip-audit refuses a hashed requirements file that contains one unhashed git line.** Export it
  unhashed and drop the git source.
- **The PyPI name `aero` belongs to an unrelated Tornado project.** `pip install aero` installs the
  wrong thing.

## 7. Open items — the operator's ordered actions, then the agent's

1. **Merge in order, and for each stacked PR wait for green on main first:**
   1. #47;
   2. #48 and #49;
   3. #50 (FULL vv-required);
   4. #51 → #52 → #53;
   5. #54 and #55, after #49;
   6. #56, after #47 and #49;
   7. #58, after #53.

   After each base merges, the next session merges `main` into the next PR branch (a conventional
   merge commit, no force-push) and waits for CI.
2. **Add the two contexts to branch protection** after their first green run on main, and add them
   to `.github/required-checks.json`:
   - `crate round-trip — Invariant 13` (after #52/#53);
   - `dependency licence scan — Invariant 5` (after #54).
3. **Repo setting:** require approval before workflows run for **all external contributors**. It is
   the primary control against fork PRs on the self-hosted runners.
4. **Review the 11 licence exceptions** in `ci/licence/exceptions.toml`.
5. **#57 constitution:**
   - no earlier than **2026-10-15**;
   - both contexts required;
   - mark it ready, comment `approved`, merge.
6. **Fill `docs/release/operator-metadata.toml`:**
   - ORCID, affiliation, ROR and funding;
   - realized research use;
   - **the AI human-review statement, in your own words.**
7. **Agent, after 1–6:** PR-15, the bump, comes last. It contains:
   - the 0.1.0 version (pyproject, `uv.lock`, CITATION);
   - CHANGELOG `[0.1.0]`;
   - this handoff `complete` with `git_sha_end`;
   - the Stage-22 prompt.

   It is a FULL vv-required run. Then dispatch `release-readiness.yml` and wait for
   `READY TO TAG v0.1.0 at <sha>`.
8. **Operator:**
   1. Tag `v0.1.0` at that sha; `tag-handoff-gate` must go green.
   2. Agent: PR-16, the README refresh.
   3. Publish the GitHub Release with the readiness artifacts (published, not a draft).
   4. QA the Zenodo record.
   5. Agent: PR-17 records the version DOI.
9. **JOSS:** submission on or after **2026-11-18**. Only the operator replies to editors and
   reviewers.

The Stage-22 prompt is authored in PR-15 at close. It does not exist yet.

## 8. Pointers for next session

- **Read first:** this file, the prompt of record, ADR-046/047/048/049, and `gh pr list`.
- **Do not re-read:** the Stage-20 campaign records. Stage 20 is closed; never reopen a lever.
- **Run first:**
  - `PATH=.venv/bin:$PATH pytest -q tests/unit tests/stage_20`;
  - `bash scripts/check_handoff_exists.sh; echo $?`, which should print 0;
  - `scripts/regenerate_status.sh --check`;
  - `gh pr checks <n>` for #47–#58;
  - the hard-don't checks:
    - both ADR-045 records are absent;
    - `git ls-remote --tags origin stage-20-evidence-2026-09-20` returns the tag;
    - the B-sentinels in ADR-039/040 are unfilled.

## 9. Artifacts produced

- **Prompt and ADRs:** the Stage-21 prompt of record; ADR-047/048/049.
- **Core code and data:** `aero/crate/` (16 modules); five result crates.
- **Scripts:**
  - `scripts/stage21_export_crates.py`, `crate_oracle.py`, `crate_ci.py`;
  - `licence_scan.py`, `check_cert_watermark.py`;
  - `check_release_tag.sh`, `release_readiness.py`;
  - `ai_usage_inventory.py`.
- **Release docs:** the JOSS paper and bib; the v0.1.0 release notes; the claims ledger;
  `.zenodo.json`.
- **Community files:** CODE_OF_CONDUCT; issue templates.
- **Tests:** several hundred new unit tests across the PRs. The suite is green on every branch:
  1290 to 1363 passed, 3 skipped, depending on the branch.

## 10. Confidence / risk

- **High:**
  - crate portability: bit-identical across five OSes and Python versions in CI, and against the
    independent oracle;
  - the licence scan's closure: it equals `uv export` for 302 and 105 packages;
  - the release gates refuse today for exactly the expected reasons.
- **Risks:**
  - **Merge sequencing.** Twelve stacked PRs need the operator's merges in order. Each stacked
    branch needs `main` merged in after its base lands.
  - **The constitution window plus sign-off gates the release.**
  - **The Ubuntu-26 runner migration** on 2026-10-19: every workflow is pinned to
    `ubuntu-24.04`, but only after #49 merges.
  - **The Stage-17 certificate expires 2027-01-20.** Readiness needs more than 30 days left, which
    is fine until about 2026-12-21.
