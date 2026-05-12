# CLAUDE.md — aero-research-platform

> Auto-loaded by Claude Code at session start. Describes what EXISTS,
> what's in-scope for this repo, and the conventions that keep it from
> drifting into the orchestrator's territory. Update this file whenever
> reality diverges from it — a stale CLAUDE.md misleads every session
> until it's fixed.

## What this project is — and isn't

**This is the AERO consumer repo for the AI Orchestrator.** Geometry,
meshing, CFD case templates, surrogate models, optimization loops,
hypothesis prompts, and evidence calculators all live here. The
orchestrator's REST + WebSocket API + Python SDK is the only contract
between the two.

**It is NOT a hub for other domains.** RF, music, protein folding,
algorithmic trading — those get their own consumer repos. This one is
aerodynamics specifically.

**Test for "does this change belong here?":**
- Would an aerodynamics researcher across many institutions also benefit?
  → yes: belongs here.
- Does it generalize across all consumer projects (auth, evidence
  schema, memory, scheduling)? → no: belongs in the orchestrator,
  file an issue there.
- Does it reference RF, antennas, protein folding, music, anything
  outside aero? → no: belongs in another consumer repo.

License: **Apache 2.0** (`LICENSE` file at repo root).

## What EXISTS

**Scaffold only (Stage 3).**

- Apache-2.0 LICENSE.
- `pyproject.toml` declaring the package, the SDK pin
  (`ai-orchestrator-client>=0.1.0a0,<0.2`), and two pluggy entry
  points (`aero_metrics` + `riblet_drag_reduction`) in the
  `ai_orchestrator_evidence` group.
- Empty `aero_research_platform/` namespace package with stub
  submodules (`evidence/`, `geometry/`, `meshing/`, `cfd/`,
  `surrogates/`, `optimization/`, `llm/`).
- Three Phase-1 campaign YAMLs in `campaigns/`.
- CI: `pytest` + `ruff` + `mypy` (Python 3.11).
- Smoke tests: package imports + every campaign YAML round-trips
  through `ai_orchestrator_client.CampaignCreate`.

Future stages flesh out the stubs.

## In-scope libraries

Explicit allowlist of aero-stack libraries that are reasonable to use here:

| Library | Role |
|---|---|
| **OpenFOAM v2412** | RANS + LES solver (on aero-research LXC) |
| **PhysicsNeMo 2.0** | NVIDIA neural-physics library; FNO + MeshGraphNet backbones |
| **PyTorch + Lightning** | Surrogate training (CUDA on cloud-burst A100s) |
| **CadQuery** | Parametric geometry (airfoil + riblet patches) |
| **gmsh** | Mesh generation (C-grids, periodic riblet strips) |
| **Stable-Baselines3** | RL for the middle loop |
| **pymoo** | Multi-objective evolutionary search |
| **numpy / scipy / pandas** | Standard data plumbing |
| **matplotlib / plotly** | Plots — keep notebooks reproducible |
| **PyYAML** | Campaign YAML parsing (already a dep) |
| **deepeval** (optional) | If/when we add an eval-campaign type |
| **chonkie** (optional) | If/when we ingest larger reference docs |

Anything outside this table — ask before adding. The orchestrator's
"Do NOT build" rules apply equally here.

## Do NOT build

- **A workflow engine.** Call the orchestrator's Prefect via
  `/orchestrate` and `/campaigns`. Never invoke `prefect.flow` directly
  from this repo.
- **Memory / evidence-bundle calculators that duplicate the orchestrator's
  builtins.** The orchestrator ships `evidence/builtin/{stats,lineage,
  compute,code_fingerprint,hardware}.py`. Register *additional* aero-specific
  calculators via the pluggy entry-point group; do not re-implement the
  built-ins.
- **Auth or bearer-token plumbing.** Use
  `ai_orchestrator_client.BearerTokenAuth(token)`.
- **A consumer hub for other domains.** This repo is aero. RF goes in
  another repo. Period.
- **MLflow / Aim / W&B.** `model_stats` + the evidence bundles are the
  authoritative experiment log.
- **K8s.** The Proxmox LXC topology is sufficient. Cloud-burst uses
  SkyPilot (the orchestrator's Phase 2.5 wrapper).

## Conventions

- Python 3.11+. Type hints required on new code.
- `ruff` + `mypy --strict` (scoped to `aero_research_platform/`).
- Tests under `tests/`; smoke tests must stay green and under 1s
  (offline — no orchestrator required).
- Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`,
  `chore:`).
- Branch: `<type>/<short-slug>`.
- Never commit to `main`. PRs require green CI + one approval (admin
  bypass enabled for solo work).
- File secrets only to `.env` (gitignored). Never hardcode an
  orchestrator token; load from env at runtime.

## Public surface used

| Symbol | Source | What for |
|---|---|---|
| `OrchestratorClient(base_url=…, auth=…)` | `ai_orchestrator_client` | Post campaigns + stream logs |
| `BearerTokenAuth(token)` | `ai_orchestrator_client` | Phase 1.7 token auth |
| `CampaignCreate(name=…, hypothesis=…, template=…, params=…)` | `ai_orchestrator_client` | Request shape |
| `CampaignTemplate(project_name=…, prompt=…, …, hitl_mode=…)` | `ai_orchestrator_client` | Embedded in CampaignCreate |
| `Campaign.iter_runs(client)` | `ai_orchestrator_client` | Streams runs as Prefect populates them |
| `client.get_evidence(campaign_id)` | `ai_orchestrator_client` | Phase 1.2 bundle |
| `client.verify_campaign_merkle(campaign_id)` | `ai_orchestrator_client` | Phase 1.5 Merkle integrity |

Anything else, check the orchestrator's
[CONSUMERS.md](https://github.com/ernesto01louis/ai-orchestrator/blob/main/CONSUMERS.md).

## When in doubt

1. Domain logic outside aero → wrong repo.
2. Generalizable infra need → file an issue against the orchestrator.
3. Not in [ROADMAP.md](ROADMAP.md) → add it to the roadmap first.
4. Can't be tested → redesign until it can.
5. Re-read "What EXISTS" above before adding something that's already there.
6. Re-read "Do NOT build" before adding orchestrator-shaped infra.

---

*Last updated: 2026-05-12, Stage 3 (initial scaffold). Phase 1
campaigns and evidence calculators are stubs; promotion happens in
Stage 4 (campaigns) and Stage 5/6 (calculators).*
