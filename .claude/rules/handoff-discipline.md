# Rule — Post-Stage Handoff Discipline

## Scope

This rule applies at the end of every stage. Loaded lazily when work
references `STAGE-NN-*-DONE-*.md`, the handoff template, or the Stop hook.

## What the handoff is

A post-stage handoff is the bridge across Claude Code's between-session
amnesia. The NEXT session reads it first to know what just happened.

It lives at `docs/handoffs/STAGE-NN-<slug>-DONE-YYYY-MM-DD.md`. The slug
matches the stage prompt's slug (e.g. `scaffolding-and-conventions` for
Stage 01).

## Mandatory frontmatter

```yaml
---
stage: NN
stage_name: "Stage NN — <name>"
status: complete | partial | blocked
date_started: YYYY-MM-DD
date_completed: YYYY-MM-DD
session_duration_hours: <number>
claude_code_version: <claude --version output>
model: <claude model id, e.g. claude-opus-4-8>
git_sha_start: <SHA>
git_sha_end: <SHA>
stage_tag: v0.0.NN
next_stage: NN+1
next_stage_name: "Stage NN+1 — <name>"
---
```

`scripts/check_handoff_exists.sh` (Stop hook) parses this frontmatter; the
five fields `stage`, `stage_name`, `status`, `date_completed`,
`git_sha_end` are required. CI on tag push also validates.

## Mandatory sections

1. **Deliverables status** — checkbox table mirroring the stage's
   DELIVERABLES list (✅ / ⚠️ / ❌ + one-line note per item)
2. **Decisions made** — bullets with rationale, including rejected
   alternatives (the *why we didn't* matters as much as the *why we did*)
3. **Deviations from the stage plan** — be honest; partial counts; note
   what got deferred
4. **Environment / dependency / schema changes** — concrete diffs:
   pyproject extras added, Postgres tables created, MinIO buckets,
   container SHA additions
5. **CI/CD changes** — workflows added/modified; new required status
   checks; branch protection diffs
6. **Gotchas discovered** — surprises future sessions need to know about
7. **Open items for the next stage** (and beyond) — concrete next-action
   items, not vague intentions. Since the optimizer refocus (ADR-013), stage
   prompts are committed to the repo: this section must confirm the **next
   stage's prompt file exists** at `docs/handoff-bundle/STAGE-(NN+1)-<slug>.md`
   (each handoff authors the next stage's prompt before session Stop).
8. **Pointers for next session** — read first / do not re-read / run
   first to verify
9. **Artifacts produced** — narrative index (full diff is in git;
   summarize)
10. **Confidence / risk note** — what you're sure about, what you're
    not, where the bus factor is high

## How the handoff is enforced

Three layers:

1. **`Stop` hook in `.claude/settings.json`** runs
   `scripts/check_handoff_exists.sh` which refuses to allow session Stop
   if the current stage's handoff is missing or has incomplete
   frontmatter.
2. **Tag-push CI check** (added in Stage 16) refuses to tag `v0.0.NN`
   without the matching handoff.
3. **Stage prompts** each end with a `POST-STAGE HANDOFF` section that
   lists required emphases for that specific stage.

## When to write

After all stage deliverables are complete, before the `v0.0.NN` tag.
Commit message convention: `docs(stage-NN): post-stage handoff`.

## What NOT to write

- Re-derive what the diff already shows (commit log is authoritative).
- Optimistic claims you can't back with evidence (link the MLflow run, the
  CI build, the artifact).
- Anything that should be in an ADR — ADRs document decisions
  permanently; handoffs document the *act* of decision-making for the
  next-session reader.
