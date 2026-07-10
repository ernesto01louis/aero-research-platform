"""Uncertainty-calibration computation — held-out ±k·std coverage (ADR-025).

Produces the :class:`~aero.surrogates._common.certificate.UncertaintyCalibration`
evidence a deep-ensemble certificate carries: how often the surrogate's
``mean ± k·std`` interval actually covered held-out truth, plus standardized-
residual diagnostics. A calibrated estimator at ``interval_k=2`` sees coverage
≈ 0.954, ``std_z ≈ 1``, ``mean_abs_z ≈ 0.798``.

Fail-loud (:class:`CalibrationError`) on degenerate inputs — in particular the
**collapsed ensemble** (all member predictions bit-identical → zero epistemic
std everywhere), which is the classic surrogate-exploitation symptom: an
optimizer steered by a zero-uncertainty surrogate believes it perfectly, which
is exactly when it must not be believed.

Pure stdlib + numpy — PLATFORM-NOT-HUB clean.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

import numpy as np

from aero.surrogates._common.certificate import UncertaintyCalibration

# Relative floor below which an epistemic std is treated as collapsed-to-zero.
_DEGENERATE_STD_RTOL = 1e-12


class CalibrationError(ValueError):
    """Calibration inputs are degenerate or inconsistent.

    Raised loud — never swallowed. A degenerate epistemic-uncertainty estimate
    (zero/negative stds, collapsed ensemble, mismatched shapes) must abort the
    certificate build, not silently produce evidence that reads as calibrated.
    """


def nominal_coverage(interval_k: float) -> float:
    """P(|Z| <= k) for standard-normal Z — what a calibrated ±k·std interval should hit."""
    if not math.isfinite(interval_k) or interval_k <= 0.0:
        raise CalibrationError(f"interval_k must be finite and > 0; got {interval_k}")
    return math.erf(interval_k / math.sqrt(2.0))


def compute_uncertainty_calibration(
    targets: Sequence[float],
    means: Sequence[float],
    stds: Sequence[float],
    *,
    interval_k: float = 2.0,
    basis: Literal["deep_ensemble", "mc_dropout"],
) -> UncertaintyCalibration:
    """Compute held-out calibration evidence for an epistemic-uncertainty estimator.

    ``targets`` are held-out truth values, ``means``/``stds`` the surrogate's
    predictive mean and epistemic std at the same points (one scalar metric,
    first-target/Cd by the platform convention).
    """
    t = np.asarray(targets, dtype=np.float64)
    m = np.asarray(means, dtype=np.float64)
    s = np.asarray(stds, dtype=np.float64)
    if t.ndim != 1 or m.ndim != 1 or s.ndim != 1:
        raise CalibrationError(
            f"targets/means/stds must be 1-D; got ndim = ({t.ndim}, {m.ndim}, {s.ndim})"
        )
    if not (t.size == m.size == s.size):
        raise CalibrationError(
            f"targets/means/stds must have equal length; got ({t.size}, {m.size}, {s.size})"
        )
    if t.size == 0:
        raise CalibrationError("cannot compute calibration from zero held-out points")
    for name, arr in (("targets", t), ("means", m), ("stds", s)):
        if not np.all(np.isfinite(arr)):
            raise CalibrationError(f"{name} contains non-finite values")
    if np.any(s < 0.0):
        raise CalibrationError(f"stds must be >= 0; min = {float(s.min())}")
    scale = max(1.0, float(np.max(np.abs(t))), float(np.max(np.abs(m))))
    if np.all(s <= _DEGENERATE_STD_RTOL * scale):
        raise CalibrationError(
            "all epistemic stds are (numerically) zero — collapsed ensemble: every member "
            "predicts identically on the held-out split, so the uncertainty estimate carries "
            "no information. Re-seed / diversify the members instead of certifying a "
            "zero-uncertainty surrogate (ADR-025)."
        )
    if np.any(s <= 0.0):
        raise CalibrationError(
            "at least one held-out point has exactly zero epistemic std — standardized "
            "residuals are undefined there. A healthy ensemble never agrees bit-identically; "
            "re-seed / diversify the members (ADR-025)."
        )

    covered = np.abs(m - t) <= interval_k * s
    z = (m - t) / s
    std_z = float(np.std(z, ddof=1)) if z.size >= 2 else 0.0
    return UncertaintyCalibration(
        basis=basis,
        n_held_out=int(t.size),
        interval_k=float(interval_k),
        nominal_coverage=nominal_coverage(interval_k),
        empirical_coverage=float(np.mean(covered)),
        mean_abs_z=float(np.mean(np.abs(z))),
        std_z=std_z,
    )
