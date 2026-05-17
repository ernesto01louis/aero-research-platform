---
description: Finish a stage — write handoff, regenerate README STATUS, PR, tag
allowed-tools: Bash, Read, Write, Edit
argument-hint: <stage-number-NN>
---

# /stage-end NN

Wraps up a stage session for `aero-research-platform`. Usage:

```
/stage-end 01
```

## What this does

1. Verifies all stage DELIVERABLES are checked off in the todo list and in
   the stage prompt's acceptance criteria.
2. Writes the post-stage handoff at
   `docs/handoffs/STAGE-NN-<slug>-DONE-YYYY-MM-DD.md` from the template at
   `docs/handoffs/_template.md`, with all 10 sections filled.
3. Runs `scripts/regenerate_status.sh` to refresh the README STATUS block.
4. Creates a `stage-NN/handoff` branch, commits the handoff with
   `docs(stage-NN): post-stage handoff`, pushes, opens PR.
5. After the handoff PR merges, tags `v0.0.NN` and pushes the tag.

## Pre-flight checks

- `pre-commit run --all-files` green
- `pytest -q tests/unit` (and any stage-specific suites) green
- All CI workflows green on the merged stage PR
- For stage 04+: `provenance-completeness` check green
- For stage 05+: `vv-required` check green
- For stage 06+: `import-platform-only` check green
- For stage 12+: any `tag=production` runs carry a `--uq` envelope

## Implementation notes

The Stop hook in `.claude/settings.json` refuses session Stop until the
handoff exists with valid frontmatter. CI on tag push validates the same.
