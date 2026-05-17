<!--
PR title must follow Conventional Commits: <type>(stage-NN): <subject>
e.g. "feat(stage-03): add OpenFOAM walking-skeleton adapter"
-->

## Summary

<!-- What this PR changes and *why*. Reference the stage this work belongs to
     and any ADR/handoff it touches. -->

## Stage

<!-- Stage NN — short stage name (e.g. "Stage 03 — Walking Skeleton OpenFOAM") -->

## Linked context

- ADR: <!-- link to docs/adrs/ADR-XXX-*.md if this PR introduces or amends one -->
- Handoff (if applicable): <!-- link to docs/handoffs/STAGE-NN-*-DONE-*.md -->
- Issue: <!-- Refs #N or "n/a" -->

## Test plan

<!-- Bulleted list of how this was tested. Required for any change that touches
     adapters/, surrogates/, provenance/, or orchestration/. -->

- [ ] `pre-commit run --all-files` green
- [ ] `pytest -q tests/unit` green
- [ ] CI workflows green (lint, type, test, docs-sync, commit-lint, plus any
      stage-specific checks)

## Provenance (for runs producing CFD or ML results)

<!-- For PRs that introduce or modify a run that produces a published-quality
     number, paste the four-tuple of one representative run:
     - git_sha: ...
     - dvc_input_hash: ...
     - container_sif_sha256: ...
     - config_hash: ...
     - mlflow_run_id: ...
     Otherwise: "n/a — scaffolding/refactor/docs". -->

## Cost projection (for PRs that change CI workflows or cloud-GPU usage)

<!-- For PRs that introduce or modify any tag=production workflow, document
     the projected $-cost; the `production-budget` CI check (live by Stage 13)
     greps the PR body for this. Otherwise: "n/a". -->

## Checklist

- [ ] Conventional Commits format on title and every commit
- [ ] No secrets in code, commits, or PR body
- [ ] Heavy deps (if any) added to optional extras, not base
- [ ] No `--no-verify`, no `--dangerously-skip-permissions`
- [ ] ADR added or amended if this changes architecture, dependencies, or
      established invariants
- [ ] Post-stage handoff updated (if completing a stage)

🤖 Generated with [Claude Code](https://claude.com/claude-code) where
applicable; the operator reviews and lands.
