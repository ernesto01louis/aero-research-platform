"""CFD-in-the-loop shape optimization (Stage 15 — the platform's product).

A direct-CFD Bayesian optimizer: parametrize a shape with a few design variables
(:mod:`aero.optimize.design_space`), propose candidates by GP + Expected-Improvement
(:mod:`aero.optimize.gp`, :mod:`aero.optimize.acquisition`, :mod:`aero.optimize.bo`), evaluate each
with **ground-truth CFD** (:mod:`aero.optimize.objective` + the existing solver/V&V stack), and
report a matched-condition CFD-verified improvement delta that exceeds ``k·U95``
(`aero.vv.reportable_compose.compose_improvement` + `OptimizationResult`). Core is stdlib + numpy +
pydantic (PLATFORM-NOT-HUB); a BoTorch/Ax backend is reserved for a future ``aero[bo]`` extra. See
ADR-026 (optimizer pin) + ADR-027 (Hard Rule 14 constitutional promotion).
"""

from __future__ import annotations

from aero.optimize.acquisition import expected_improvement
from aero.optimize.airfoil_case import ShapedLaminarAirfoil
from aero.optimize.bo import BayesianOptimizer, BOConfig, Observation
from aero.optimize.design_space import DesignSpace, DesignVariable
from aero.optimize.gp import GaussianProcess, GPConfig
from aero.optimize.objective import CFDObjective, ObjectiveEval

__all__ = [
    "BOConfig",
    "BayesianOptimizer",
    "CFDObjective",
    "DesignSpace",
    "DesignVariable",
    "GPConfig",
    "GaussianProcess",
    "ObjectiveEval",
    "Observation",
    "ShapedLaminarAirfoil",
    "expected_improvement",
]
