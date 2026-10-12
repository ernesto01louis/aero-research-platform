---
stage: 21
stage_name: "Stage 21 — Release: Portable Bundles + Hardening + v0.1.0"
status: partial
date_started: 2026-10-11
date_completed: 2026-10-12
session_duration_hours: 1
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-5-5
git_sha_start: 83baa43225cd9a5f9684a0481b8502b6004fa49c
git_sha_end: 83baa43225cd9a5f9684a0481b8502b6004fa49c
stage_tag: v0.1.0
next_stage: 22
next_stage_name: "Stage 22 — Rigid-Flapping Optimization"
---

# Stage 21 — Release: Portable Bundles + Hardening + v0.1.0 — IN PROGRESS (partial)

> **Stage 21 is OPEN and `partial`.** This file exists from the first Stage-21 commit so that the
> Stop hook (`scripts/check_handoff_exists.sh`) passes once `.aero-stage` is 21. It is updated in
> place until the stage closes. Do not create a second Stage-21 handoff: the hook picks the
> newest-mtime file and the README generator the lexicographically last.
>
> The stage prompt of record is `docs/handoff-bundle/STAGE-21-release-portable-bundles.md`. Its
> "Operator decisions recorded at stage open" table and its record-faithful wording table bind this
> stage.

## 1. Deliverables status

| # | Deliverable (verbatim from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | Bookkeeping (PR-01) | ⚠️ | `.aero-stage` 21, prompt of record, Hard Rule 16 fixed, template comments fixed, this handoff — in review |
| 2 | Result crates — the RESULTS-MUST-TRAVEL bundle (ADR-047) | ❌ | not started |
| 3 | Round-trip CI (`crate-roundtrip.yml`) | ❌ | not started |
| 4 | Dependency licence scan (ADR-048) | ❌ | not started |
| 5 | Hardening — a closed list | ❌ | not started |
| 6 | JOSS + Zenodo — ends at "ready to submit" | ❌ | not started |
| 7 | Governance, then v0.1.0 last | ❌ | not started |

## 2. Decisions made

- **Stage scope** is ADR-046 S1, not re-argued.
- **Operator decisions D1–D4 (2026-10-11).** These are recorded in the prompt of record:
  - D1: GPL-3.0-compatible licence allowlist, scoped; dvc stays in base.
  - D2: record-faithful wording; ADR-046 untouched.
  - D3: crate content licence CC-BY-4.0.
  - D4: evidence tags for the Stage 12/15/16/17 SHAs, after a gitleaks scan.
- **The bundle is called a "result crate" in code** (`aero/crate/`). Rejected: "bundle", which
  already names the Stage-20 evidence dicts, the precice manifest, the Stage-17 corpus and
  `docs/handoff-bundle/`.
- **v0.1.0 is Stage 21's stage tag.** There is no `v0.0.21` tag. Rejected: two tags on one commit.
  A second tag would invite a second GitHub Release and therefore a second Zenodo DOI.

## 3. Deviations from the stage plan

None yet.

## 4. Environment / dependency / schema changes

None yet.

## 5. CI/CD changes

None yet.

## 6. Gotchas discovered

- **The handoff template broke the Stop hook.** Its inline `# …` comments became part of the
  frontmatter values, because both awk parsers read the whole rest of the line. A `status:` copied
  verbatim from the template failed the hook. Fixed in PR-01 by moving the comments onto their own
  lines; the parsers are unchanged.
- **No committed `ReportableResult` JSON reloads into its own model.** The computed fields are
  written by default `model_dump_json()` and rejected by `extra='forbid'`. The prompt's "Why this
  stage" section has this and the other audit findings.

## 7. Open items for the next stage (and beyond)

- The Stage-22 prompt (`docs/handoff-bundle/STAGE-22-rigid-flapping-optimization.md`) is authored
  at Stage-21 close.

## 8. Pointers for next session

- **Read first:**
  - `docs/handoff-bundle/STAGE-21-release-portable-bundles.md`;
  - ADR-046;
  - this file.
- **Run first:**
  - `PATH=.venv/bin:$PATH pytest -q tests/unit tests/stage_20`;
  - `bash scripts/check_handoff_exists.sh; echo $?`, which should print 0;
  - `scripts/regenerate_status.sh --check`.

## 9. Artifacts produced

- `docs/handoff-bundle/STAGE-21-release-portable-bundles.md`: the stage prompt of record.

## 10. Confidence / risk

- **High:** the scope and the operator decisions.
- **Risks:**
  - The constitution micro-PR's ≥72 h window plus the operator's sign-off gate the release.
  - The Ubuntu-26 runner migration on 2026-10-19 lands mid-stage.
