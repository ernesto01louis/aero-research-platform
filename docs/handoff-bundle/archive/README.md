# `docs/handoff-bundle/archive/` — superseded planning documents (provenance only)

These files are **historical**. They record the planning state *before* the
optimizer-mission refocus (ADR-013, 2026-06-10). Nothing here governs current work — the
governing scope is `docs/handoff-bundle/00-MISSION-AND-SCOPE.md`, the current map is
`docs/handoff-bundle/README-handoff.md`. They are kept so the supersession chain is
auditable.

## Contents

| File | What it is | Superseded by |
|---|---|---|
| `00-CONTEXT-project-brief.md` | The original generic "do-everything" project brief, pasted alongside every early stage prompt (never previously committed). | `00-MISSION-AND-SCOPE.md` + ADR-013 |
| `00-MISSION-AND-SCOPE-original-two-flagship.md` | The operator's first refocus draft (flapping + riblet as co-flagships; optimizer treated as backlog). | the reworked `00-MISSION-AND-SCOPE.md` + ADR-013 |
| `original-roadmap/STAGE-10..16-*.md` | The original operator-side Stage 10–16 prompts (automotive surrogate zoo, preCICE, DPW/HLPW V&V, multi-cloud router, NeMo agent, literature miner, hardening). | the Stage 10–20 map in `README-handoff.md` + ADR-013 |

## Pending verbatim commit

The four document classes above are committed **verbatim from the operator's clean
source files** (the copies available to the agent during the refocus session carried
UTF-8 rendering corruption, so they were not transcribed). They land here when the
operator pastes the clean originals — committed unmodified except for a one-line
`> ARCHIVED — superseded by ADR-013 (2026-06-10); does not govern.` banner at the top of
each.

## Convention going forward (ADR-013)

Stage prompts are **committed to the repo** from Stage 10 on, at
`docs/handoff-bundle/STAGE-NN-<slug>.md`. Each stage's post-stage handoff authors the
next stage's prompt (handoff-discipline rule). The originals above predate that
convention and were operator-side only.
