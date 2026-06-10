# `docs/handoff-bundle/archive/` — superseded planning documents (provenance only)

These files are **historical**. They record the planning state *before* the
optimizer-mission refocus (ADR-013, 2026-06-10). Nothing here governs current work — the
governing scope is `docs/handoff-bundle/00-MISSION-AND-SCOPE.md`, the current map is
`docs/handoff-bundle/README-handoff.md`. They are kept so the supersession chain is
auditable.

## Contents (committed verbatim from the operator's clean source files)

| File | What it is | Superseded by |
|---|---|---|
| `00-CONTEXT-project-brief.md` | The original generic "do-everything" project brief, pasted alongside every early stage prompt. | `../00-MISSION-AND-SCOPE.md` + ADR-013 |
| `00-MISSION-AND-SCOPE-original-two-flagship.md` | The operator's first refocus draft (flapping + riblet as co-flagships; optimizer treated as backlog). | the reworked `../00-MISSION-AND-SCOPE.md` + ADR-013 |
| `original-roadmap/README-handoff.md` | The original 16-stage bundle overview. | `../README-handoff.md` (Stage 10–20 map) + ADR-013 |
| `original-roadmap/PROMPT-00-proxmox-inspection.md`, `PROMPT-CONTEXT-RESTORE.md` | The original recon / context-restore prompts. | n/a (historical) |
| `original-roadmap/STAGE-01..16-*.md` | The original operator-side Stage 01–16 prompts (incl. the automotive surrogate zoo + MoE at 09–10, DPW/HLPW V&V at 12, multi-cloud router at 13, NeMo agent at 14, literature miner at 15). | the Stage 10–20 map in `../README-handoff.md` + ADR-013 |

Committed **verbatim** (only end-of-file/whitespace normalization by pre-commit hooks);
their location under `archive/` plus this README mark them superseded — no per-file banner.
The chat-attachment channel that delivered earlier copies corrupted UTF-8 lossily
(em-dashes, Greek letters, box-drawing destroyed); these were instead committed from the
operator's clean on-disk copies.

## Architecture reviews (now committed)

- **`architecture-review-original-compass-artifact.md`** (here) — the **pre-correction,
  tubercle-locked first review** ("build a small, sharp thesis, not a platform"). This is the
  **opposite** of the current mission (the platform IS the deliverable; ADR-013). Kept for
  provenance only; **does not govern**.
- **`docs/architecture/BRIEFING-architecture-review-for-independent-challenge.md`** (not here —
  it's a live, non-normative *reference*, not a superseded original) — the corrected
  general-platform briefing, partially adopted per ADR-013 (its capability-layer framing +
  verify-every-optimum principle are core).

## Convention going forward (ADR-013)

Stage prompts are **committed to the repo** from Stage 10 on, at
`docs/handoff-bundle/STAGE-NN-<slug>.md`. Each stage's post-stage handoff authors the
next stage's prompt (handoff-discipline rule). The originals above predate that
convention and were operator-side only.
