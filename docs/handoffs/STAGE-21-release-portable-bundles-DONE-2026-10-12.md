---
stage: 21
stage_name: "Stage 21 — Release: Portable Bundles + Hardening + v0.1.0"
status: complete
date_started: 2026-10-11
date_completed: 2026-10-15
session_duration_hours: 20
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-5-5
git_sha_start: 83baa43225cd9a5f9684a0481b8502b6004fa49c
git_sha_end: c2a00b4369b8cb8aa16a57dce93dff657f9af26b
stage_tag: v0.1.0
next_stage: 22
next_stage_name: "Stage 22 — Rigid-Flapping Optimization"
---

# Stage 21 — Release: Portable Bundles + Hardening + v0.1.0 — COMPLETE (v0.1.0 ready to tag)

> **Stage 21 is `complete`.** Every deliverable is merged on main. The constitution PR (#57) merged
> on 2026-10-15 after its 72 h window and the operator's sign-off, and **PR-15**, the v0.1.0
> bump, is the last PR of the stage. `git_sha_end` is PR-15's bump commit (`c2a00b4`). The commit
> after it is docs-only (this handoff and the README), so the squash-merged commit that gets tagged
> has the same code tree; `check_release_tag.sh` checks exactly that.
>
> **The limitation v0.1.0 carries:** the optimizer has never been run on a flapping-wing case, and
> v0.1.0 makes no flapping-wing optimization claim. It is in the body of the release notes, the
> paper, the CHANGELOG, `CITATION.cff` and `.zenodo.json`.
>
> **What is left is operator-gated (§7):** the `v0.1.0` tag, the README refresh after it (PR-16),
> the GitHub Release (which mints the Zenodo version DOI), PR-17 for that DOI, and the JOSS
> submission on or after 2026-11-18.
>
> - **Do not create a second Stage-21 handoff.** The Stop hook picks the newest-mtime file and the
>   README generator the lexicographically last.
> - **The prompt of record** is `docs/handoff-bundle/STAGE-21-release-portable-bundles.md`. Its
>   operator-decision table (D1–D4) and its record-faithful wording table bind this stage.
> - **The plan of record** is `docs/adrs/ADR-047` / `048` / `049` (#48).

## 1. Deliverables status

| # | Deliverable (verbatim from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | Bookkeeping (PR-01) | ✅ | **#47** (merged `caf3908`): `.aero-stage` 21, prompt of record, Hard Rule 16 → Stage 21, template comments moved to their own lines, this handoff |
| 2 | Result crates — the RESULTS-MUST-TRAVEL bundle (ADR-047) | ✅ merged | **#50** core hardening, the prerequisite (`ff009e6`). **#60**, which replaced #51: `aero/crate/` format v1, plus an RO-Crate 1.3 conformance fix (`c7bca16`). **#53** the five committed crates (`32f52f3`) under `crates/`, an independent oracle, `test_crate_committed` |
| 3 | Round-trip CI (`crate-roundtrip.yml`) | ✅ merged; **required** | **#52** (`0be02b6`): clean Linux 3.12/3.13, macOS, Windows and floor read legs. **#53** adds the committed crates (pinned digests plus the oracle) and a Windows `core.autocrlf=true` checkout leg. All legs green; the external roc-validator now passes too |
| 4 | Dependency licence scan (ADR-048) | ✅ merged; **required** | **#54** (`35ed4a4`): `scripts/licence_scan.py`, `ci/licence/`, required job `dependency licence scan — Invariant 5`. 302 packages: 291 allowed, 9 identified, 2 admitted, 0 fail. Also the license-audit watermark repair |
| 5 | Hardening — a closed list | ✅ | Done: H-01..H-36 except H-34/H-35 (P2, ledgered per ADR-049 R4) and the optional PR-04/PR-12. **#49** CI supply chain (`f52c5b3`, before 2026-10-19). **#50** finite U95, IEEE-exact RSS, lazy loguru, version single-source, repo-root, extra=forbid. **#55** release-tag gate plus readiness (`42607a6`). **#56** docs truth (`ffe93a3`). The version-string policy is recorded in ADR-049 R3 (#48, `15721a4`) |
| 6 | JOSS + Zenodo — ends at "ready to submit" | ✅ | **#58** (merged `9c0fbc5`): paper, bib (20 verified DOIs), generated AI disclosure, `.zenodo.json`, CITATION refresh, release notes, claims ledger. **#63** (`aa6a602`) the operator's metadata: ORCID, affiliation, funding, research use, the AI human-review statement (paper now 1437 words). Only `submission_date` stays a sentinel until the operator submits, on or after **2026-11-18** |
| 7 | Governance, then v0.1.0 last | ✅ ready to tag | **#57** (merged `dc7b762`, 2026-10-15T12:05Z): Invariant 13, Invariant 5 reworded, text fixes, ADR-047/048/049 accepted, after the ≥72 h window (opened 2026-10-12T12:01Z), both new contexts required, and the operator's sign-off comment (2026-10-14). **PR-15**: the 0.1.0 bump, CHANGELOG `[0.1.0] - 2026-10-15`, the Stage-22 prompt, two readiness-checker fixes. The tag itself is the operator's (§7) |

**PR map** (all squash-merged to main; merged by the agent at the operator's request):

| PR | Branch | Base | What |
|---|---|---|---|
| #47 | stage-21-open | main | PR-01 bookkeeping |
| #48 | stage-21-adrs | stage-21-open | PR-02 ADR-047/048/049 (proposed) |
| #49 | stage-21-ci-supply-chain | main | PR-03 SHA pins, ubuntu-24.04, locked installs, injection/REAP fixes, registry and hygiene test |
| #50 | stage-21-core-hardening | main | PR-05 FULL vv-required; finite floats, exact RSS, lazy loguru, version |
| ~~#51~~ → #60 | stage-21-crate → stage-21-crate-r2 | main | PR-06 `aero/crate/` format v1 (#51 closed: one header was 104 > 100 chars) |
| #52 | stage-21-crate-ci | #51 | PR-07 crate round-trip CI |
| #53 | stage-21-crates | #52 | PR-08 the five committed crates |
| #54 | stage-21-licence-scan | #49 | PR-09 dependency licence scan |
| #55 | stage-21-release-gate | #49 | PR-10 release-tag gate + readiness |
| #56 | stage-21-docs-truth | #47 | PR-11 docs match reality, community files |
| #58 | stage-21-joss | #53 | PR-13 JOSS / Zenodo / CITATION / release notes / claims ledger |
| #61 | stage-21-handoff-merges | main | this handoff after the stack merged |
| #62 | stage-21-addendum | main | ADR-050 (proposed), the Stage-22 retry item, the Dependabot ignore rule |
| #63 | stage-21-orcid | main | the operator's JOSS/Zenodo metadata |
| #64 | stage-21-signoff-vv-status | main | the exceptions' reviewer = the operator; the V&V report is not ALL GREEN |
| #57 | stage-21-constitution | main | PR-14 constitution micro-PR, merged last before the bump |
| PR-15 | stage-21-release-v0.1.0 | main | the v0.1.0 bump (FULL vv-required) plus this handoff `complete` |

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

- **Merges.** At first the auto-mode classifier refused agent merges. On 2026-10-12 the operator
  explicitly asked the agent to do the steps itself, and the agent then squash-merged, in order:
  #47, #50, #49, #48, #60, #52, #53, #54, #55, #56, #58.
  - For each one it first merged `main` into the branch (conventional merge commits, no
    force-push), checked locally, and waited for every required context.
  - It never pushed to a branch while a self-hosted job on that branch was running.
- **#51 was replaced by #60.** One commit header was 104 characters, over commit-lint's 100.
  Rewriting it would need a force-push, which the hooks forbid. #60 is the same tree with that
  commit re-made.
- **Dependabot opened #59** (`dorny/paths-filter` 3.0.4 → 4.0.3). The operator closed it on
  2026-10-13: v3.0.4 is kept deliberately, because that action runs in the secret-bearing
  vv-required job. A Dependabot ignore rule for its majors keeps it from reopening.
- **The external-review addendum (2026-10-11):**
  - A (version policy) is recorded in ADR-049 R3, and Development Status is 3 - Alpha (#50). The
    bump itself is PR-15.
  - B (a hosted-runner CPU-only end-to-end number) is now **ADR-050, proposed** (operator
    decision 2026-10-13: ADR now, build after v0.1.0). It is ledgered.
  - C (per-evaluation retry in the optimizer loop) is a **Stage-22 pre-registration item**
    (operator decision 2026-10-13), ledgered. The loop already skips and counts a failed solve
    (S8); it lacks a bounded retry and a recorded failure reason.

  Neither reopens Stage 20 or coupled-FSI restart.
- **Not done (optional or ledgered):**
  - PR-04, the vv-required restructure (optional, propose-first);
  - PR-12, a hosted run of `tests/stage_*` (optional);
  - a `regenerate_status.sh` unit test (ledgered).
- **H-34 and H-35 (P2) were NOT done.** They are ledgered per ADR-049 R4 (#56):
  - H-34: path-safe patterns on the preCICE directory fields, plus `shlex.quote`;
  - H-35: 3MF zip caps.

  H-36, the `[cu12]` extra name, is done (#50).
- **The licence exceptions' `reviewer` field** names the operator, who approved all 11 on
  2026-10-14 in the #57 sign-off comment; the agent prepared them (#64).
- **Two bugs in `scripts/release_readiness.py`**, found by running it on PR-15 before tagging:
  - the limitation check matched raw source, so a phrase wrapped across lines or set in bold was
    "missing" from the notes and the paper;
  - the install-text check flagged CONSTITUTION Invariant 1's own warning ("never `pip install
    aero`").

  Both are fixed in PR-15, with tests that run the two checks on the real checkout. The unit tests
  had used one-line synthetic fixtures, which is why they passed.
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
- **Branch protection now requires 12 contexts.** The two new ones were added after their first
  green runs on main:
  - `crate round-trip — Invariant 13`, at `0be02b6`;
  - `dependency licence scan — Invariant 5`, at `35ed4a4`.

  Strict mode is kept, and the registry equals protection (#56).
- **Fork-PR workflow approval** is `all_external_contributors` (set 2026-10-12; was
  `first_time_contributors`).

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
- **numpy reductions differ in the last bit across CPUs** (SIMD paths). This was seen with
  identical numpy and pydantic versions on the CI runners vs. the host. A test that pins bytes
  computed by numpy at test time is machine-dependent. The self-test paired fixture is now a
  committed snapshot (#60), and a freshness test checks it to within 1e-12.
- **Check commit headers before pushing.** A header over 100 characters cannot be fixed without a
  force-push, so it costs a replacement PR. Validate a range before every push with:

  ```sh
  git log --format=%s origin/main..HEAD | awk 'length > 100'
  ```
- **The self-hosted queue paces merges.** Each push to a same-repo PR starts `vv-smoke` (about 30
  min) and `provenance-completeness`, and these hold the two runners that the required
  `vv-required` job needs. Strict mode allows one merge per main movement, so a stack of N PRs
  costs N CI cycles.

## 7. Open items — what is left, in order

**Done by the close (2026-10-15):** the merges (§1); both new contexts required; fork approval set
to all external contributors; the licence exceptions approved; the operator metadata filled; #57
merged; PR-15 merged; the Stage-22 prompt written.

1. **Agent:** after PR-15 merges, run `python3 -I scripts/release_readiness.py --gate release
   --online` on main and dispatch `gh workflow run release-readiness.yml -f version=0.1.0 --ref
   main`. Both must print `READY TO TAG v0.1.0 at <sha>`.
2. **Operator:** tag that sha and push the tag:

   ```sh
   git tag -a v0.1.0 <sha> -m "aero-research-platform v0.1.0"
   git push origin v0.1.0
   ```

   `tag-handoff-gate` must go green. If it goes red, the operator deletes the tag (propose-first),
   the handoff is fixed, and the tag is re-cut.
3. **Agent:** PR-16, the README STATUS refresh, as the **first** PR after the tag. The tagged
   tree's README reads "(not yet tagged)" by design.
4. **Operator:** download the readiness run's `release-artifacts-v0.1.0`, check `sha256sum -c
   SHA256SUMS`, confirm the Zenodo toggle is on, and publish the GitHub Release (published, not a
   draft or pre-release) with `docs/release/RELEASE-NOTES-v0.1.0.md` and those artifacts. Then QA
   the Zenodo record: creators, `gpl-3.0-or-later`, v0.1.0, and the limitation in the description.
5. **Agent:** PR-17 records the version DOI in `docs/release/zenodo.md` and `CITATION.cff`.
6. **JOSS:** the operator submits on or after **2026-11-18** and sets `submission_date` then.
   Before submitting, regenerate the AI disclosure (`--write --ref origin/main`) and run
   `release_readiness.py --gate joss --online`. **Only the operator replies to editors and
   reviewers.**
7. **Post-v0.1.0:** Stage 22 (`docs/handoff-bundle/STAGE-22-rigid-flapping-optimization.md`,
   which carries addendum C as a pre-registration item); ADR-050 (proposed, addendum B); H-34 and
   H-35 (ledgered).

The Stage-22 prompt exists: `docs/handoff-bundle/STAGE-22-rigid-flapping-optimization.md`.

## 8. Pointers for next session

- **Read first:** this file, the prompt of record, ADR-046/047/048/049, and `gh pr list`.
- **Do not re-read:** the Stage-20 campaign records. Stage 20 is closed; never reopen a lever.
- **Run first:**
  - `PATH=.venv/bin:$PATH pytest -q tests/unit tests/stage_20`;
  - `bash scripts/check_handoff_exists.sh; echo $?`, which should print 0;
  - `scripts/regenerate_status.sh --check`;
  - `gh pr list` (open at the close: #21 only, which is unrelated and left alone);
  - the hard-don't checks:
    - both ADR-045 records are absent;
    - `git ls-remote --tags origin stage-20-evidence-2026-09-20` returns the tag;
    - the B-sentinels in ADR-039/040 are unfilled.

## 9. Artifacts produced

- **Prompts and ADRs:** the Stage-21 prompt of record; the Stage-22 prompt; ADR-047/048/049
  (accepted); ADR-050 (proposed).
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
  - **The tag and the Release are the operator's.** Until both happen, v0.1.0 exists only as the
    merged commit.
  - **The Ubuntu-26 runner migration** on 2026-10-19 is covered: every workflow is pinned to
    `ubuntu-24.04` (#49 merged).
  - **The Stage-17 certificate expires 2027-01-20.** Readiness needs more than 30 days left, which
    is fine until about 2026-12-21.
