# Context Restoration Prompt — aero-research-platform

**When to use this file**: paste its full contents (or attach it) into a fresh Claude
chat to bring Claude back up to speed on the aerodynamics research platform project
without re-doing the deep research from scratch.

---

## Hi Claude — please read this first.

You and I (Ernesto Louis, GitHub `ernesto01louis`) have been working together on
building **`aero-research-platform`** — a fully open-source, peer-review-grade
aerodynamics research platform. This message catches you up on the state of that
work so we can pick up where we left off.

## The deliverables produced so far

You produced three deep research artifacts and one handoff bundle for me. They are
the canonical references for everything in this project. If I have them attached to
this conversation, please skim them; if not, ask me for them by name:

1. **Pass 1 — Architecture & Build Specification**
   Three-plane design (control / compute / physics-ML), full stack: OpenFOAM-ESI,
   SU2 v8, NekRS, PyFR, JAX-Fluids 2.0, NVIDIA PhysicsNeMo (DoMINO / Transolver /
   FIGConvNet / X-MeshGraphNet / MoE), preCICE 3, NVIDIA NeMo Agent Toolkit + AI-Q
   Blueprint fork, Prefect 3 + Covalent orchestration, DVC + MLflow + Postgres +
   MinIO provenance, V&V vs NASA TMR / AIAA DPW-7 / HLPW-5, UQpy / Dakota. Compute
   on Proxmox LXC + RunPod (H100) + Lambda Labs (A100) + Vast.ai. 80-week phased
   roadmap.

2. **Pass 2 — SOTA Literature Review (2024–2026)**
   24 domains, encyclopedic. Key findings I asked you to remember:
   - Hybrid RANS-LES + WMLES is current practical SOTA; vanilla PINNs are a dead
     end for turbulent flows; neural operators (Transolver, DoMINO, FIGConvNet,
     GeoTransolver) are the frontier.
   - Industry consolidation: Synopsys–Ansys $35B (closed July 17, 2025), Siemens–
     Altair ~$10B (closed March 26, 2025), Cadence Fidelity bundles NUMECA +
     Pointwise + Cascade.
   - Funding: Neural Concept $100M Series C, Luminary Cloud $72M Series B,
     PhysicsX $155M Series B near-unicorn, CoreWeave–Monolith acquired November 5,
     2025.
   - Agentic CFD is working: ChatCFD 82.1% success, MetaOpenFOAM, OpenFOAMGPT,
     Foam-Agent 2.0.
   - AeroSHARK riblets validated in-flight (Lufthansa Group, 22 aircraft).

3. **Pass 3 — Claude Code Handoff Best-Practices Guide**
   Four-layer memory model (CLAUDE.md + `.claude/rules/` + STAGE-N + post-stage
   handoff), spec-driven workflow (GitHub Spec-Kit + BMAD synthesis), deterministic
   guardrails via hooks + branch protection, walking skeleton ordering, the
   detailed post-stage handoff template (§4.2), MCP server recommendations,
   token budget heuristics (≤30K session-start), the four-fold provenance
   tuple (git SHA + DVC hash + container SIF SHA256 + config hash), and concrete
   countermeasures for the RF bundle's failure modes.

4. **The handoff bundle itself** — 19 files for Claude Code to use to build the
   platform stage by stage:
   - `PROMPT-00-proxmox-inspection.md` — SSH-based read-only reconnaissance of my
     Proxmox host
   - `README-handoff.md` — bundle overview, 16-stage ordering, cross-stage
     guardrails
   - `00-CONTEXT-project-brief.md` — distilled invariants, pasted alongside every
     stage prompt
   - `STAGE-01-scaffolding-and-conventions.md` through
     `STAGE-16-hardening-and-release-v0.1.md` — one prompt per Claude Code session

## My decisions (so you don't re-litigate them)

- Scientific rigor: peer-reviewable, thesis-grade.
- Fully standalone — no coupling to any prior orchestrator.
- All physics scope at end state; no rush. Long dev time is fine.
- All four AI areas in scope: surrogates, autonomous design, agentic, literature
  mining.
- "Next state of the art" — weight recent work heavily.
- License posture: GPL-3 / LGPL-3 / Apache-2.0 / BSD-3 only — no proprietary blobs.
- No hard time cutoff on the literature.
- Depth: encyclopedic when forced to choose.
- Stage granularity: **finer — 12-16 stages, each one a focused session**. The
  bundle uses 16.
- Final plan: research first → SSH inspection prompt → handoff bundle.

## Where we left off

(Tell Claude in your own words: which stage you're at, what's been done in the
real repo, any divergence from the bundle, any post-stage handoffs already
written.)

## How I want you to behave going forward

1. **Search first when relevant.** For anything that might have changed since your
   training cutoff (PhysicsNeMo container tags, SU2 releases, preCICE versions,
   funding announcements, license changes, regulatory developments), search the
   web — don't answer from memory.
2. **Defer to the three research artifacts on architecture and SOTA.** They are the
   project's canonical references. If something in them is wrong or outdated,
   propose an update via a new pass, don't silently override.
3. **Defer to the handoff bundle on Claude Code build mechanics.** The 19 files
   were designed together; don't reinvent the structure mid-flight.
4. **Propose first, execute later** for anything destructive or persistent — same
   rule as in the bundle's CLAUDE.md.
5. **Tone**: collaborative, opinionated where the research supports it,
   thesis-grade rigor, no fluff. I prefer prose over bullet-stews. Long answers are
   fine when warranted; bullet-stews are not.

## What I might ask you to do

Common follow-up requests, listed so you have the right reflexes:

- "Resume the bundle and write Stage XX" — pick up the same structure (REQUIREMENTS
  / ROLE / GOAL / WHY / HOW / BEFORE-YOU-START-READ / GUARDRAILS / DELIVERABLES /
  PROPOSE-FIRST / POST-STAGE-HANDOFF), tag `v0.0.XX` at the end.
- "Update Pass 1 / Pass 2 / Pass 3 with new info from [paper / release / news]"
  — re-research, update, mark the update in the artifact.
- "Claude Code finished Stage XX; here's the post-stage handoff — what should
  I tell it for Stage XX+1?" — read the handoff, then refresh the STAGE-(XX+1)
  prompt to acknowledge any deviations or carry-overs.
- "I hit a problem at Stage XX; help me debug" — switch from bundle-author mode
  to collaborator mode, but still propose-first on destructive ops.
- "Generate a paper / thesis / talk from what we have" — separate task; the
  platform is the tool, the paper is downstream.

## What you should ask me when you start

If any of these are unclear from my next message, ask before doing anything:

- Which stage are we at? Has Claude Code already done anything in the real repo?
- Do you have the three research artifacts (Pass 1, 2, 3) accessible to me in
  this conversation, or should I work from your summaries only?
- Has the Proxmox inspection been done? Is the inventory report available?
- Are there any post-stage handoffs from earlier sessions I should read first?

---

End of context-restoration prompt. Ready to continue.
