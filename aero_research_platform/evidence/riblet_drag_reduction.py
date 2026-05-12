"""Riblet drag-reduction evidence calculator (stub).

Discovered by the orchestrator's pluggy plugin host via the
``ai_orchestrator_evidence`` entry-point group. Currently returns an
empty list. Real implementation lands in Stage 5/6, at which point
it will compute DR% vs the smooth-wall baseline at matched Re_theta
and verify against the Bechert 1997 / MicroTau / NASA TMR reference
bounds declared in the campaign hypothesis.
"""
from __future__ import annotations

from typing import Any


def hook(campaign: Any, runs: list[Any]) -> list[Any]:
    """compute_evidence hook impl. Stub returns []."""
    return []


__all__ = ["hook"]
