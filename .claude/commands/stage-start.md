---
description: Begin a new stage — load the stage prompt, prior handoff, and update .aero-stage
allowed-tools: Bash, Read, Write, Edit
argument-hint: <stage-number-NN>
---

# /stage-start NN

Begins a new stage session for `aero-research-platform`. Usage:

```
/stage-start 02
```

## What this does

1. Updates `.aero-stage` at repo root from the current value to NN.
2. Reads the previous stage's post-stage handoff at
   `docs/handoffs/STAGE-(NN-1)-*-DONE-*.md` and summarizes its open items
   and pointers for the current session.
3. Reads `00-CONTEXT-project-brief.md` and `STAGE-NN-*.md` (operator
   pastes these alongside the slash invocation if not in the bundle dir).
4. Lists the stage's DELIVERABLES as a checklist and creates corresponding
   todo entries via TodoWrite.
5. Reminds about propose-first gates and the post-stage-handoff requirement
   at end-of-stage.

## Implementation notes

This is a documentation-only slash command — the actual stage-start
workflow happens in the conversation. The operator pastes
`00-CONTEXT-project-brief.md` and `STAGE-NN-*.md` at session start; this
slash invocation simply structures the work.
