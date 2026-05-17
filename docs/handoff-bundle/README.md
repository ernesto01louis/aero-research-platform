# `docs/handoff-bundle/`

The 16-stage handoff bundle and Pass 3 best-practices guide. Operator
commits these once Stage 01 is in place.

Bundle contents (one file per stage plus context):

- `00-CONTEXT-project-brief.md` — distilled invariants pasted alongside
  every stage prompt
- `STAGE-01-scaffolding-and-conventions.md` through
  `STAGE-16-hardening-and-release-v0.1.md` — one prompt per Claude Code
  session
- `README-handoff.md` — bundle overview, 16-stage ordering, cross-stage
  guardrails
- `PROMPT-00-proxmox-inspection.md` — SSH-based read-only Proxmox
  reconnaissance (already executed; output at
  `/root/aero-inspect/proxmox-inventory-2026-05-16.md` on host;
  committed to `docs/architecture/` by Stage 02)
- `PROMPT-CONTEXT-RESTORE.md` — context-restoration prompt for any new
  Claude conversation about the project

Plus the Pass 3 Claude Code best-practices guide (four-layer memory,
spec-driven workflow, hooks, MCP servers, token budget heuristics,
post-stage-handoff template rationale).

Stage prompts and the project brief are referenced explicitly by name in
each stage's "BEFORE YOU START — READ" section.
