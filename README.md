# aero-research-platform

[![CI](https://github.com/ernesto01louis/aero-research-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/ernesto01louis/aero-research-platform/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)

**Status: Pre-alpha.** Scaffold only — campaigns commit verbatim from the design brief, evidence calculators are stubs. Stage 4 lands real geometry/meshing/CFD; Stage 5/6 lands surrogates + optimization + populated evidence calculators.

This is the **consumer** repo for aerodynamics research running on top of the [AI Orchestrator](https://github.com/ernesto01louis/ai-orchestrator). The orchestrator is generic; all aero domain code lives here.

## Three-loop architecture

| Loop | Where | Cadence |
|---|---|---|
| **Outer** — LLM hypothesis generation | `aero_research_platform/llm/` | Per round (days) |
| **Middle** — RL / evolutionary search via neural surrogates | `aero_research_platform/{surrogates,optimization}/` | Per design (minutes) |
| **Inner** — CFD validation + surrogate retraining | `aero_research_platform/{cfd,meshing,geometry}/` | Per case (hours) |

See [VISION.md](VISION.md) for the full architectural rationale.

## Bootstrap

1. **Clone** and create a venv:
   ```sh
   git clone https://github.com/ernesto01louis/aero-research-platform.git
   cd aero-research-platform
   python3.11 -m venv .venv && source .venv/bin/activate
   pip install -e '.[dev]'
   ```

2. **Point at your orchestrator** (defaults to `127.0.0.1:8000`):
   ```sh
   cp .env.example .env
   $EDITOR .env
   ```

3. **Run the smoke tests:**
   ```sh
   pytest -q
   ```
   This proves the package imports and every campaign YAML in `campaigns/` round-trips cleanly through the SDK's `CampaignCreate` — entirely offline.

4. **Run a campaign** (requires a live orchestrator + the `aero-research` deploy target wired in `config.json`):
   ```sh
   # Via the SDK:
   python -c "from pathlib import Path; import yaml; from ai_orchestrator_client import OrchestratorClient, CampaignCreate; \
              data = yaml.safe_load(Path('campaigns/01-naca0012-baseline.yaml').read_text()); \
              with OrchestratorClient(base_url='http://127.0.0.1:8000') as c: print(c.start_campaign(CampaignCreate(**data)))"
   # Or via raw REST — see RUNBOOK.md
   ```

## Layout

| Path | Purpose |
|---|---|
| `aero_research_platform/` | Python package (stubs today) |
| `campaigns/` | Phase 1 campaign YAMLs — three to start |
| `sky/` | SkyPilot specs (CPU + A100 bursts) — placeholders |
| `scripts/` | Operator glue — placeholders |
| `tests/` | Smoke tests; load-bearing contract check |
| `notebooks/` | Exploratory Jupyter — gitkept |
| `data/`, `results/` | Bulk data — `.gitignore`'d |

## Why this exists

See [VISION.md](VISION.md). TL;DR — the orchestrator is a generic agentic platform with citation-grade evidence bundles; this repo is the first real consumer that hammers the [CONSUMERS.md](https://github.com/ernesto01louis/ai-orchestrator/blob/main/CONSUMERS.md) contract on a real domain.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Conventional Commits, branch protection on `main`, CI required for merge.

## License

[Apache 2.0](LICENSE).
