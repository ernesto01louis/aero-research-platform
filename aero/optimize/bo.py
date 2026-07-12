"""Direct-CFD Bayesian optimization ask/tell loop (Stage 15).

A small, backend-free BO over a :class:`~aero.optimize.design_space.DesignSpace`: seed with a
Latin-hypercube initial design, then fit a GP (:mod:`aero.optimize.gp`) and pick the next point by
maximizing Expected Improvement (:mod:`aero.optimize.acquisition`) over a discrete unit-cube
candidate pool (no gradient optimizer needed in <=6-D). Every proposed point is CFD-evaluated by the
caller (Hard Rule 14 — direct CFD, no surrogate optimum); ``tell`` records the observed value.

stdlib + numpy + pydantic only (PLATFORM-NOT-HUB). ADR-026.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from aero.optimize.acquisition import expected_improvement
from aero.optimize.design_space import DesignSpace
from aero.optimize.gp import GaussianProcess, GPConfig

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_assignment=True, validate_default=True)


class BOConfig(BaseModel):
    """Bayesian-optimization loop settings."""

    model_config = _STRICT

    n_init: int = Field(..., ge=1, description="Latin-hypercube initial design size.")
    n_iter: int = Field(..., ge=0, description="EI-guided iterations after the initial design.")
    xi: float = Field(
        default=0.01, ge=0.0, description="EI exploration margin (standardized-y scale)."
    )
    candidate_pool: int = Field(default=2048, ge=16, description="Discrete EI candidate pool size.")
    seed: int = Field(default=0, description="RNG seed (LHS + candidate pool).")
    gp: GPConfig = Field(default_factory=GPConfig)


class Observation(BaseModel):
    """One CFD-evaluated (design, objective value) pair."""

    model_config = _STRICT

    design: tuple[float, ...]
    value: float
    mlflow_run_id: str | None = None


class BayesianOptimizer:
    """Ask/tell BO. ``ask`` returns the next physical design; ``tell`` records its CFD value."""

    def __init__(self, space: DesignSpace, config: BOConfig, *, maximize: bool = True) -> None:
        self.space = space
        self.config = config
        self.maximize = maximize
        self._obs: list[Observation] = []
        self._init = space.lhs(config.n_init, seed=config.seed)  # physical (n_init, d)
        self._rng = np.random.default_rng(config.seed + 1)

    def ask(self) -> np.ndarray:
        """The next design to CFD-evaluate (physical coordinates)."""
        k = len(self._obs)
        if k < self.config.n_init:
            return np.asarray(self._init[k], dtype=np.float64)
        # Fit the GP on the standardized observations and maximize EI over a discrete pool.
        x_unit = np.asarray(
            [self.space.to_unit(np.asarray(o.design)) for o in self._obs], dtype=np.float64
        )
        y = np.asarray([o.value for o in self._obs], dtype=np.float64)
        gp = GaussianProcess(self.config.gp).fit(x_unit, y)
        pool = self._rng.random((self.config.candidate_pool, self.space.dim()))  # unit cube
        mean, std = gp.predict(pool)
        best = float(np.max(y) if self.maximize else np.min(y))
        ei = expected_improvement(mean, std, best, maximize=self.maximize, xi=self.config.xi)
        return self.space.from_unit(pool[int(np.argmax(ei))])

    def tell(self, x: np.ndarray, value: float, *, mlflow_run_id: str | None = None) -> None:
        self._obs.append(
            Observation(
                design=tuple(float(v) for v in np.asarray(x, dtype=np.float64)),
                value=float(value),
                mlflow_run_id=mlflow_run_id,
            )
        )

    @property
    def observations(self) -> tuple[Observation, ...]:
        return tuple(self._obs)

    @property
    def n_candidates(self) -> int:
        """Number of CFD-evaluated designs the incumbent was selected from (best-of-N)."""
        return len(self._obs)

    @property
    def incumbent(self) -> tuple[np.ndarray, float]:
        """The best CFD-observed design + value (fail-loud if nothing told yet)."""
        if not self._obs:
            raise RuntimeError("BayesianOptimizer.incumbent before any tell()")
        vals = np.asarray([o.value for o in self._obs], dtype=np.float64)
        idx = int(np.argmax(vals) if self.maximize else np.argmin(vals))
        return np.asarray(self._obs[idx].design, dtype=np.float64), float(self._obs[idx].value)
