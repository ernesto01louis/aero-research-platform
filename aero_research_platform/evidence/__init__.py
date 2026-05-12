"""Evidence-bundle calculators for aero campaigns.

Each submodule exposes a ``hook`` object decorated with
``@hookimpl(specname="compute_evidence")`` that the orchestrator's
pluggy plugin host discovers via the ``ai_orchestrator_evidence``
entry-point group declared in ``pyproject.toml``.

Stubs today (return ``[]``). Real calculators land in Stage 5/6.
"""
from __future__ import annotations

__all__: list[str] = []
