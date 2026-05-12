"""Geometry sanity tests for the NASA-TMR sharp-TE NACA 0012."""

from __future__ import annotations

import numpy as np
import pytest

from aero_research_platform.geometry.naca import (
    NACA_SHARP_TE_X,
    naca_closed_loop,
    naca_half,
    thickness,
)


def test_sharp_te_closes_to_zero() -> None:
    """NACA 0012 standard polynomial must close at x = 1.008930411365."""
    y_te = thickness(np.array([NACA_SHARP_TE_X]), t=0.12)
    assert abs(float(y_te[0])) < 1e-6, f"sharp-TE residual = {float(y_te[0])}"


def test_blunt_te_is_non_zero_at_x_eq_1() -> None:
    """Sanity: at x=1 the polynomial is NOT closed (~1.26e-3)."""
    y1 = thickness(np.array([1.0]), t=0.12)
    assert float(y1[0]) > 1.0e-3
    assert float(y1[0]) < 2.0e-3


def test_max_thickness_about_12pct_at_x_30pct() -> None:
    """NACA 0012 peaks at y/c ≈ 0.06 near x/c ≈ 0.3."""
    xs = np.linspace(0.0, 1.0, 401)
    ys = thickness(xs, t=0.12)
    i_max = int(np.argmax(ys))
    assert 0.25 < float(xs[i_max]) < 0.35
    assert 0.0595 < float(ys[i_max]) < 0.0605


def test_naca_half_endpoints_zero() -> None:
    x, y = naca_half(t=0.12, n_points=257)
    assert y[0] == 0.0
    assert y[-1] == 0.0
    assert abs(float(x[0])) < 1e-12
    assert abs(float(x[-1]) - NACA_SHARP_TE_X) < 1e-12


def test_naca_half_cosine_clustering() -> None:
    """First and last spacings must be much smaller than mid-chord spacings."""
    x, _ = naca_half(t=0.12, n_points=257)
    dx = np.diff(x)
    assert dx[0] < 0.05 * dx[len(dx) // 2]
    assert dx[-1] < 0.05 * dx[len(dx) // 2]


def test_closed_loop_orientation_and_count() -> None:
    """Closed loop = 2*n - 1 points, upper first (positive y), then lower."""
    n = 129
    x, y = naca_closed_loop(t=0.12, n_per_side=n)
    assert len(x) == 2 * n - 1
    assert len(y) == 2 * n - 1
    # First point is TE upper (y = 0 at TE, just after that y > 0).
    assert y[1] > 0.0
    # Last point is TE lower (y = 0 at TE, just before that y < 0).
    assert y[-2] < 0.0
    # Symmetry: upper half is the mirror image of the lower half.
    np.testing.assert_allclose(y[:n], -y[n - 1 :][::-1], atol=1e-12)


@pytest.mark.parametrize("n_points", [3, 17, 257, 1024])
def test_naca_half_accepts_arbitrary_n(n_points: int) -> None:
    x, y = naca_half(t=0.12, n_points=n_points)
    assert len(x) == n_points
    assert len(y) == n_points


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        naca_half(t=0.0)
    with pytest.raises(ValueError):
        naca_half(t=1.5)
    with pytest.raises(ValueError):
        naca_half(n_points=2)
