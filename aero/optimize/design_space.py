"""Design space for CFD-in-the-loop shape optimization (Stage 15).

A ``DesignSpace`` is an ordered set of bounded ``DesignVariable``s. The Bayesian optimizer works
in the **unit cube** (`to_unit`/`from_unit`) so one isotropic GP length-scale is meaningful across
variables of different physical scale; `lhs` draws a seeded Latin-hypercube initial design;
`as_named` maps a raw vector back to the ``{name: value}`` dict the ``OptimizationResult`` records.

Strict, frozen pydantic (`.claude/rules/fail-loud-pydantic.md`); stdlib + numpy + pydantic only
(PLATFORM-NOT-HUB).
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_assignment=True, validate_default=True)


class DesignVariable(BaseModel):
    """One bounded design variable (a shape parameter, e.g. NACA-4 max camber)."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    low: float = Field(..., description="Lower bound (inclusive).")
    high: float = Field(..., description="Upper bound (inclusive).")

    @model_validator(mode="after")
    def _ordered(self) -> DesignVariable:
        if not self.high > self.low:
            raise ValueError(f"design variable {self.name!r}: high ({self.high}) must exceed low")
        return self


class DesignSpace(BaseModel):
    """An ordered, bounded design space; the optimizer operates on it via the unit cube."""

    model_config = _STRICT

    variables: tuple[DesignVariable, ...] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _unique_names(self) -> DesignSpace:
        names = [v.name for v in self.variables]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate design-variable names: {names}")
        return self

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(v.name for v in self.variables)

    def dim(self) -> int:
        return len(self.variables)

    def bounds(self) -> np.ndarray:
        """(d, 2) array of [low, high] per variable."""
        return np.asarray([[v.low, v.high] for v in self.variables], dtype=np.float64)

    def to_unit(self, x: np.ndarray) -> np.ndarray:
        """Map physical coordinates into the unit cube [0, 1]^d."""
        b = self.bounds()
        return np.asarray(
            (np.asarray(x, dtype=np.float64) - b[:, 0]) / (b[:, 1] - b[:, 0]), dtype=np.float64
        )

    def from_unit(self, u: np.ndarray) -> np.ndarray:
        """Map unit-cube coordinates back to physical bounds."""
        b = self.bounds()
        return np.asarray(
            b[:, 0] + np.asarray(u, dtype=np.float64) * (b[:, 1] - b[:, 0]), dtype=np.float64
        )

    def clip(self, x: np.ndarray) -> np.ndarray:
        """Clip physical coordinates to the bounds."""
        b = self.bounds()
        return np.asarray(
            np.clip(np.asarray(x, dtype=np.float64), b[:, 0], b[:, 1]), dtype=np.float64
        )

    def lhs(self, n: int, *, seed: int) -> np.ndarray:
        """Seeded Latin-hypercube sample of ``n`` points, in PHYSICAL coordinates, shape (n, d)."""
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        rng = np.random.default_rng(seed)
        d = self.dim()
        u = np.empty((n, d), dtype=np.float64)
        for j in range(d):
            # One stratified sample per interval [i/n, (i+1)/n), then permute across points.
            edges = (np.arange(n) + rng.random(n)) / n
            u[:, j] = rng.permutation(edges)
        return self.from_unit(u)

    def as_named(self, x: np.ndarray) -> dict[str, float]:
        """Map a raw physical vector to ``{name: value}`` (for OptimizationResult.design_variables)."""
        x = np.asarray(x, dtype=np.float64)
        if x.shape != (self.dim(),):
            raise ValueError(f"expected shape ({self.dim()},), got {x.shape}")
        return {v.name: float(x[i]) for i, v in enumerate(self.variables)}
