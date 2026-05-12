"""Aero metrics evidence calculator (stub).

Discovered by the orchestrator's pluggy plugin host via the
``ai_orchestrator_evidence`` entry-point group. Currently returns an
empty list. Real implementation lands in Stage 5/6, at which point
it will report per-run Cl/Cd/y+ deltas vs hypothesis bounds.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


def hook(campaign: Any, runs: list[Any]) -> list[Any]:
    """compute_evidence hook impl. Stub returns []."""
    return []


__all__ = ["hook"]
