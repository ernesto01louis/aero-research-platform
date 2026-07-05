"""Unsteady post-processing toolkit (Stage 11).

Turns transient CFD force/pressure traces into the derived quantities the flapping
optimizer's objective is built from — Strouhal/frequency, phase-averaged loads,
thrust / input power / propulsive efficiency, the viscous/pressure force split, and the
periodic-steady-state (cycle-convergence) check — from a **converged limit cycle**.

PLATFORM-NOT-HUB clean: stdlib + numpy + pydantic only, strict pydantic. It is a
library (no CLI group): the OpenFOAM adapter's ``load()`` and the V&V cases call it, and
the optimizer (Stage 15) will call it directly. Its per-cycle samples
(:class:`CycleSamples`) are the seam Stage 12's statistical-U95 (batch-means / N_eff)
consumes.
"""

from __future__ import annotations

from aero.postprocess._base import Signal
from aero.postprocess.cycle_detection import CycleConvergenceReport, detect_cycle_convergence
from aero.postprocess.efficiency import MotionKinematics, PropulsiveMetrics, propulsive_metrics
from aero.postprocess.forces import ForceDecomposition, decompose_drag
from aero.postprocess.frequency import FrequencyEstimate, dominant_frequency, strouhal
from aero.postprocess.phase_averaging import (
    CycleSamples,
    PhaseAverage,
    phase_average,
    segment_cycles,
)

__all__ = [
    "CycleConvergenceReport",
    "CycleSamples",
    "ForceDecomposition",
    "FrequencyEstimate",
    "MotionKinematics",
    "PhaseAverage",
    "PropulsiveMetrics",
    "Signal",
    "decompose_drag",
    "detect_cycle_convergence",
    "dominant_frequency",
    "phase_average",
    "propulsive_metrics",
    "segment_cycles",
    "strouhal",
]
