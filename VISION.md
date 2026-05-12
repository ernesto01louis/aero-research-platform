# VISION — aero-research-platform

## Why this exists

Modern aerodynamic optimization is bottlenecked on three things:

1. **CFD throughput.** A single high-fidelity RANS+LES case takes hours; a sweep takes weeks. Surrogates are the answer, but they need ground-truth data to train, and they need a *campaign* to know what to learn next.
2. **Hypothesis generation.** Most papers test variations of someone else's idea. We want a system that proposes the next test from prior evidence — the **outer loop**.
3. **Evidence custody.** Reviewers (and future-you) need to know *what was measured*, *how*, *against what reference*, and *with what code at which commit*. Notebooks rot; campaign artifacts under a Merkle root do not.

## Three-loop architecture

The orchestrator provides the agentic plumbing. This repo provides the aero loops.

```
┌──────────────────────────────────────────────────────────────┐
│  OUTER LOOP — LLM hypothesis generation                      │
│  llm/hypothesis_prompts.py                                   │
│  Reads: prior campaigns' evidence bundles                    │
│  Writes: next CampaignCreate(hypothesis=…, params=…)         │
│  Frequency: per research round (days)                        │
└─────────────────────┬────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────┐
│  MIDDLE LOOP — RL/evolutionary search via surrogates         │
│  surrogates/{fno_airfoil,meshgraphnet}.py + optimization/    │
│  Reads: trained FNO / MGN surrogates                         │
│  Writes: candidate (h/s, t/s, target s+) tuples              │
│  Frequency: per design point (minutes)                       │
└─────────────────────┬────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────┐
│  INNER LOOP — CFD validation + surrogate retraining          │
│  cfd/templates/ + meshing/airfoil_cmesh.py + …               │
│  Reads: OpenFOAM v2412 templates                             │
│  Writes: postProcessing/forceCoeffs1/ → DR%, Cl, Cd, y+      │
│  Frequency: per case (hours on aero-research LXC;            │
│             escalates to SkyPilot A100 burst for LES)        │
└──────────────────────────────────────────────────────────────┘
```

The orchestrator wraps each loop iteration in a citation-grade run (Phase 1.5 SHA256 manifest + Phase 1.2 evidence bundle), so every iteration is reproducible, signed, and Merkle-rooted into the parent campaign.

## Platform vs. hub

This repo is a *consumer* of the orchestrator, not an extension of it.

- **The orchestrator is generic.** It handles routing, memory, evidence, gates, SSH targets, Prefect flows. It does not know what a riblet is.
- **This repo is aero-only.** Geometry, meshing, CFD case templates, surrogate architectures, hypothesis prompts, evidence calculators — all here. The orchestrator never imports from this repo; this repo imports only from `ai-orchestrator-client` (the public SDK).

The contract is documented in the orchestrator's [CONSUMERS.md](https://github.com/ernesto01louis/ai-orchestrator/blob/main/CONSUMERS.md). The orchestrator's [CLAUDE.md](https://github.com/ernesto01louis/ai-orchestrator/blob/main/CLAUDE.md) governs that side. This repo's [CLAUDE.md](CLAUDE.md) governs this side.

If a domain need cannot be served by the orchestrator's public surface, **file an issue against the orchestrator** — do not patch around it here.

## Inspirations (references, not deps)

This work draws on several recent agentic-CAE efforts. Each is a *reference*; none is a dependency.

- **PhysicsX — Large Physics Models.** End-to-end neural physics on industrial geometries; informs the surrogates layer.
- **NVIDIA agentic CAE** (Pablo Hermoso Moreno, et al.). Agent-orchestrated CFD pipelines; informs the inner-loop wrapping pattern.
- **BeyondMath.** Neural CFD with a hypothesis-driven UX; informs the outer loop's UX expectations.
- **MIT Buehler multi-agent science.** Multi-agent literature synthesis; informs how the outer loop will consume `references/` content for hypothesis grounding.

## Apache 2.0

The platform is Apache 2.0. This consumer is Apache 2.0. Use it commercially; do not re-license without contributing the changes back.

## What is *not* in scope

- A general-purpose CAE hub. This repo is *aero* — wings, riblets, RANS, LES, surrogates trained on aero data.
- A workflow engine. Call the orchestrator's Prefect via `/orchestrate` and `/campaigns`.
- A custom evidence-bundle format. The orchestrator's Phase 1.2 RO-Crate-1.2/WRROC is sufficient. We register calculators via pluggy.
- A vector DB or memory store. The orchestrator's L1-L5 memory + Hindsight covers this.
- A custom auth layer. Use the orchestrator's Phase 1.7 bearer-token (`BearerTokenAuth` in the SDK).
