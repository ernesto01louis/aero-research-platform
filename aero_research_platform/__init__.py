"""aero-research-platform — consumer of ai-orchestrator.

This package holds aero domain code (geometry, meshing, CFD case
templates, surrogate models, optimization loops, hypothesis prompts,
and evidence calculators) that runs ON TOP of the AI Orchestrator
platform via its public SDK (``ai-orchestrator-client``) and REST/WS
surface. The orchestrator stays domain-neutral.

See ``CLAUDE.md`` and ``VISION.md`` at the repo root for context.
"""
from __future__ import annotations

__version__ = "0.0.0"
__all__: list[str] = []
