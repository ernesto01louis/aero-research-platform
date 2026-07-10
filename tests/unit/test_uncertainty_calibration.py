"""ADR-025 — calibration computation: coverage recovery + degenerate-input guards.

A well-specified estimator (targets genuinely drawn from N(mean, std)) must
recover the nominal ±2·std coverage and std_z ≈ 1; collapsed / degenerate
uncertainty must raise :class:`CalibrationError` rather than certify.

Pure numpy — runs in the required CI unit job.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from aero.surrogates._common.calibration import (
    CalibrationError,
    compute_uncertainty_calibration,
    nominal_coverage,
)


def test_nominal_coverage_formula() -> None:
    assert nominal_coverage(2.0) == pytest.approx(math.erf(2.0 / math.sqrt(2.0)))
    assert nominal_coverage(2.0) == pytest.approx(0.9545, abs=1e-4)
    assert nominal_coverage(1.0) == pytest.approx(0.6827, abs=1e-4)


def test_nominal_coverage_rejects_bad_k() -> None:
    with pytest.raises(CalibrationError):
        nominal_coverage(0.0)
    with pytest.raises(CalibrationError):
        nominal_coverage(float("nan"))


def test_calibrated_gaussian_recovers_nominal() -> None:
    rng = np.random.default_rng(42)
    n = 2000
    means = rng.uniform(-1.0, 1.0, size=n)
    stds = rng.uniform(0.05, 0.5, size=n)
    targets = means + stds * rng.standard_normal(n)
    cal = compute_uncertainty_calibration(
        targets.tolist(), means.tolist(), stds.tolist(), interval_k=2.0, basis="deep_ensemble"
    )
    assert cal.n_held_out == n
    assert cal.nominal_coverage == pytest.approx(0.9545, abs=1e-4)
    assert cal.empirical_coverage == pytest.approx(cal.nominal_coverage, abs=0.02)
    assert cal.std_z == pytest.approx(1.0, abs=0.05)
    # E|Z| for standard normal is sqrt(2/pi) ~ 0.798.
    assert cal.mean_abs_z == pytest.approx(math.sqrt(2.0 / math.pi), abs=0.05)


def test_overconfident_estimator_shows_low_coverage() -> None:
    """Stds 10x too small — the exploitation symptom the Stage-16 gate watches."""
    rng = np.random.default_rng(7)
    n = 1000
    means = rng.uniform(-1.0, 1.0, size=n)
    true_std = 0.2
    targets = means + true_std * rng.standard_normal(n)
    claimed_stds = np.full(n, true_std / 10.0)
    cal = compute_uncertainty_calibration(
        targets.tolist(),
        means.tolist(),
        claimed_stds.tolist(),
        interval_k=2.0,
        basis="deep_ensemble",
    )
    assert cal.empirical_coverage < 0.3
    assert cal.std_z > 5.0


def test_collapsed_ensemble_raises() -> None:
    with pytest.raises(CalibrationError, match="collapsed ensemble"):
        compute_uncertainty_calibration(
            [0.1, 0.2, 0.3], [0.1, 0.2, 0.3], [0.0, 0.0, 0.0], basis="deep_ensemble"
        )


def test_single_zero_std_raises() -> None:
    with pytest.raises(CalibrationError, match="exactly zero epistemic std"):
        compute_uncertainty_calibration(
            [0.1, 0.2, 0.3], [0.1, 0.2, 0.3], [0.01, 0.0, 0.01], basis="deep_ensemble"
        )


def test_negative_std_raises() -> None:
    with pytest.raises(CalibrationError, match=">= 0"):
        compute_uncertainty_calibration(
            [0.1, 0.2], [0.1, 0.2], [0.01, -0.01], basis="deep_ensemble"
        )


def test_length_mismatch_raises() -> None:
    with pytest.raises(CalibrationError, match="equal length"):
        compute_uncertainty_calibration([0.1, 0.2], [0.1], [0.01], basis="deep_ensemble")


def test_empty_raises() -> None:
    with pytest.raises(CalibrationError, match="0 held-out"):
        compute_uncertainty_calibration([], [], [], basis="deep_ensemble")


def test_non_finite_raises() -> None:
    with pytest.raises(CalibrationError, match="non-finite"):
        compute_uncertainty_calibration(
            [float("nan"), 0.2], [0.1, 0.2], [0.01, 0.01], basis="deep_ensemble"
        )


def test_single_point_refuses_to_certify() -> None:
    # ADR-025 honest-absence / FAIL-LOUD: the ddof=1 std_z is undefined at n=1,
    # so calibration refuses rather than fabricating a definite 0.0.
    with pytest.raises(CalibrationError, match="held-out point"):
        compute_uncertainty_calibration([0.1], [0.12], [0.05], basis="deep_ensemble")
