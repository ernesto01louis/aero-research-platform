"""Expected-Improvement acquisition for Bayesian optimization (Stage 15).

Closed-form Gaussian EI over a GP posterior (mean, std). Reimplemented here (pure numpy, ``math.erf``
— no scipy) rather than imported from ``aero/surrogates/_common/infill.py`` so ``aero/optimize`` is
self-contained and branch-independent (that EI is ADR-025 surrogate-in-the-loop machinery, absent
from ``main``). ADR-026.
"""

from __future__ import annotations

import math

import numpy as np

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)
_erf_vec = np.vectorize(math.erf)


def _normal_cdf(z: np.ndarray) -> np.ndarray:
    return np.asarray(0.5 * (1.0 + _erf_vec(z / _SQRT2)), dtype=np.float64)


def _normal_pdf(z: np.ndarray) -> np.ndarray:
    return np.asarray(np.exp(-0.5 * z**2) / _SQRT2PI, dtype=np.float64)


def expected_improvement(
    mean: np.ndarray, std: np.ndarray, best: float, *, maximize: bool = True, xi: float = 0.0
) -> np.ndarray:
    """Expected improvement of candidates over the current best-observed ``best``.

    ``mean``/``std`` are the GP posterior at the candidates; ``xi`` is an exploration margin.
    For ``maximize`` the improvement is ``mean - best - xi`` (flipped for minimization). Where
    ``std == 0`` the EI degenerates to ``max(improvement, 0)`` (deterministic). Always ``>= 0``.
    """
    mean = np.asarray(mean, dtype=np.float64)
    std = np.asarray(std, dtype=np.float64)
    improvement = (mean - best - xi) if maximize else (best - mean - xi)
    ei = np.zeros_like(improvement)
    pos = std > 0.0
    z = np.zeros_like(improvement)
    z[pos] = improvement[pos] / std[pos]
    ei[pos] = improvement[pos] * _normal_cdf(z[pos]) + std[pos] * _normal_pdf(z[pos])
    ei[~pos] = np.maximum(improvement[~pos], 0.0)
    return np.maximum(ei, 0.0)
