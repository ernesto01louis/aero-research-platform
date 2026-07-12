"""A minimal Gaussian-process surrogate of the objective (Stage 15 Bayesian optimization).

Pure-numpy GP regression — the only genuinely-new numerics the direct-CFD optimizer needs. Fit in
the unit cube with a standardized target; predict posterior mean + std at query points; feed those
to the EI acquisition (:mod:`aero.optimize.acquisition`). No scipy, no torch — ~40 lines of numpy
via ``numpy.linalg.cholesky`` + triangular solves (PLATFORM-NOT-HUB, matching the platform's
"lightweight, no heavy deps" precedent). ADR-026.

The design space is tiny (2-6 DVs) and the budget small (~15-30 CFD evals), so a plain GP with a
fixed length-scale (optionally a coarse LML grid-search) is entirely adequate — BoTorch/Ax would be
overkill and is reserved for a future ``aero[bo]`` extra.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_assignment=True, validate_default=True)


def _pairwise_sq_dists(a: np.ndarray, b: np.ndarray, *, length_scale: np.ndarray) -> np.ndarray:
    """Squared distances between rows of ``a`` and ``b`` scaled by per-dimension length scales."""
    aw = a / length_scale
    bw = b / length_scale
    a2 = np.sum(aw**2, axis=1)[:, None]
    b2 = np.sum(bw**2, axis=1)[None, :]
    return np.asarray(np.maximum(a2 + b2 - 2.0 * aw @ bw.T, 0.0), dtype=np.float64)


def rbf_kernel(
    a: np.ndarray, b: np.ndarray, *, length_scale: np.ndarray, signal_var: float
) -> np.ndarray:
    """Squared-exponential (RBF) kernel."""
    k = signal_var * np.exp(-0.5 * _pairwise_sq_dists(a, b, length_scale=length_scale))
    return np.asarray(k, dtype=np.float64)


def matern52_kernel(
    a: np.ndarray, b: np.ndarray, *, length_scale: np.ndarray, signal_var: float
) -> np.ndarray:
    """Matérn-5/2 kernel (smoother tails than RBF; the BO default)."""
    r = np.sqrt(_pairwise_sq_dists(a, b, length_scale=length_scale))
    s5 = np.sqrt(5.0)
    k = signal_var * (1.0 + s5 * r + 5.0 / 3.0 * r**2) * np.exp(-s5 * r)
    return np.asarray(k, dtype=np.float64)


class GPConfig(BaseModel):
    """Gaussian-process hyperparameters (in UNIT-cube distance)."""

    model_config = _STRICT

    kernel: Literal["rbf", "matern52"] = "matern52"
    length_scale: float = Field(
        default=0.3, gt=0.0, description="Isotropic length scale (unit cube)."
    )
    signal_var: float = Field(default=1.0, gt=0.0, description="Signal variance (standardized y).")
    noise_var: float = Field(default=1.0e-6, ge=0.0, description="Observation noise variance.")
    jitter: float = Field(
        default=1.0e-9, gt=0.0, description="Diagonal jitter for Cholesky stability."
    )


class GaussianProcess:
    """A fitted GP over (unit-cube X, standardized y). Not a pydantic model (holds numpy state)."""

    def __init__(self, config: GPConfig | None = None) -> None:
        self.config = config or GPConfig()
        self._x: np.ndarray | None = None
        self._y_mean = 0.0
        self._y_std = 1.0
        self._L: np.ndarray | None = None
        self._alpha: np.ndarray | None = None

    def _kernel(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        ls = np.full(a.shape[1], self.config.length_scale, dtype=np.float64)
        fn = matern52_kernel if self.config.kernel == "matern52" else rbf_kernel
        return fn(a, b, length_scale=ls, signal_var=self.config.signal_var)

    def fit(self, x_unit: np.ndarray, y: np.ndarray) -> GaussianProcess:
        """Fit on unit-cube inputs ``x_unit`` (n, d) and targets ``y`` (n,). Standardizes y."""
        x_unit = np.atleast_2d(np.asarray(x_unit, dtype=np.float64))
        y = np.asarray(y, dtype=np.float64).ravel()
        if x_unit.shape[0] != y.shape[0]:
            raise ValueError(f"X rows ({x_unit.shape[0]}) != y ({y.shape[0]})")
        self._x = x_unit
        self._y_mean = float(y.mean())
        self._y_std = float(y.std()) or 1.0
        yz = (y - self._y_mean) / self._y_std
        k = self._kernel(x_unit, x_unit)
        k[np.diag_indices_from(k)] += self.config.noise_var + self.config.jitter
        self._L = np.linalg.cholesky(k)
        self._alpha = np.linalg.solve(self._L.T, np.linalg.solve(self._L, yz))
        return self

    def predict(self, x_unit: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Posterior (mean, std) at unit-cube query points, un-standardized to y's scale."""
        if self._x is None or self._L is None or self._alpha is None:
            raise RuntimeError("GaussianProcess.predict called before fit")
        xq = np.atleast_2d(np.asarray(x_unit, dtype=np.float64))
        ks = self._kernel(self._x, xq)  # (n_train, n_query)
        mean_z = ks.T @ self._alpha
        v = np.linalg.solve(self._L, ks)
        kss = np.full(xq.shape[0], self.config.signal_var, dtype=np.float64)  # k(x,x) diagonal
        var_z = np.maximum(kss - np.sum(v**2, axis=0), 0.0)
        mean = mean_z * self._y_std + self._y_mean
        std = np.sqrt(var_z) * self._y_std
        return mean, std
