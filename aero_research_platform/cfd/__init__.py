"""OpenFOAM v2412 case templates, runners, and post-processors (stub).

Inner-loop validation in the three-loop architecture (see VISION.md).
Stage 4+ lands ``templates/`` (simpleFoam + k-omega SST presets),
runners that exec OpenFOAM via the orchestrator's deploy target, and
post-processors that read ``postProcessing/forceCoeffs1/`` etc.
"""
from __future__ import annotations

__all__: list[str] = []
