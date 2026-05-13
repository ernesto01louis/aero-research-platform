"""Geometry tests for blade-riblet profile and s+/s mapping."""

from __future__ import annotations

import numpy as np
import pytest

from aero_research_platform.geometry.riblet import (
    BECHERT_BLADE_H_OVER_S,
    BECHERT_BLADE_T_OVER_S,
    BladeRibletSpec,
    blade_period_profile,
    blade_strip_profile,
    s_from_s_plus,
    s_plus_from_s,
)


def test_bechert_defaults_match_paper() -> None:
    """Default h/s = 0.5 and t/s = 0.02 (Bechert 1997 Fig 5 blade variant)."""
    assert BECHERT_BLADE_H_OVER_S == 0.5
    assert BECHERT_BLADE_T_OVER_S == 0.02


def test_blade_period_profile_geometry() -> None:
    """Single period: floor → flank up → tip → flank down → floor.

    For pitch s=1, h/s=0.5, t/s=0.02 the 6 points are
        (0, 0), (0.49, 0), (0.49, 0.5), (0.51, 0.5), (0.51, 0), (1, 0).
    """
    spec = BladeRibletSpec(pitch_s=1.0)
    y, z = blade_period_profile(spec)
    assert y.shape == (6,)
    assert z.shape == (6,)
    np.testing.assert_allclose(y, [0.0, 0.49, 0.49, 0.51, 0.51, 1.0], atol=1e-12)
    np.testing.assert_allclose(z, [0.0, 0.0, 0.5, 0.5, 0.0, 0.0], atol=1e-12)


def test_h_over_s_matches_spec() -> None:
    spec = BladeRibletSpec(pitch_s=2.5e-3, h_over_s=0.5)
    _, z = blade_period_profile(spec)
    measured_h = float(z.max())
    assert measured_h == pytest.approx(spec.h_over_s * spec.pitch_s, rel=1e-12)


def test_t_over_s_matches_spec() -> None:
    spec = BladeRibletSpec(pitch_s=1.0, t_over_s=0.02)
    y, _ = blade_period_profile(spec)
    # Blade thickness is the gap between the two flank y-coordinates.
    measured_t = float(y[3] - y[2])
    assert measured_t == pytest.approx(spec.t_over_s * spec.pitch_s, rel=1e-12)


def test_strip_profile_n_points_shares_valley_corners() -> None:
    """Adjacent periods share their valley corner: 5*n + 1 points, not 6*n."""
    spec = BladeRibletSpec(pitch_s=1.0)
    for n in (1, 2, 4, 8):
        y, z = blade_strip_profile(spec, n_pitches=n)
        assert len(y) == 5 * n + 1
        assert len(z) == 5 * n + 1
        # Valley start and end on the wall.
        assert z[0] == 0.0
        assert z[-1] == 0.0


def test_strip_profile_spans_n_pitches() -> None:
    spec = BladeRibletSpec(pitch_s=1.5)
    y, _ = blade_strip_profile(spec, n_pitches=4)
    np.testing.assert_allclose(y[0], 0.0, atol=1e-12)
    np.testing.assert_allclose(y[-1], 4 * 1.5, atol=1e-12)


def test_s_from_s_plus_inverts() -> None:
    """Round-trip s ↔ s+ at canonical (u_tau, nu)."""
    u_tau = 0.05
    nu = 1.6667e-7
    for s_plus in (5.0, 17.0, 40.0):
        s = s_from_s_plus(s_plus, u_tau=u_tau, nu=nu)
        s_plus_back = s_plus_from_s(s, u_tau=u_tau, nu=nu)
        assert s_plus_back == pytest.approx(s_plus, rel=1e-12)


def test_s_from_s_plus_matches_definition() -> None:
    """s+ = s u_tau / nu ⇒ s = s+ nu / u_tau."""
    s = s_from_s_plus(s_plus=17.0, u_tau=0.05, nu=1e-6)
    assert s == pytest.approx(17.0 * 1e-6 / 0.05, rel=1e-12)


def test_invalid_pitch_raises() -> None:
    with pytest.raises(ValueError):
        BladeRibletSpec(pitch_s=0.0)
    with pytest.raises(ValueError):
        BladeRibletSpec(pitch_s=-1.0)


def test_invalid_h_over_s_raises() -> None:
    with pytest.raises(ValueError):
        BladeRibletSpec(pitch_s=1.0, h_over_s=0.0)
    with pytest.raises(ValueError):
        BladeRibletSpec(pitch_s=1.0, h_over_s=-0.1)


def test_invalid_t_over_s_raises() -> None:
    with pytest.raises(ValueError):
        BladeRibletSpec(pitch_s=1.0, t_over_s=0.0)
    with pytest.raises(ValueError):
        BladeRibletSpec(pitch_s=1.0, t_over_s=1.0)
    with pytest.raises(ValueError):
        BladeRibletSpec(pitch_s=1.0, t_over_s=1.5)


def test_s_from_s_plus_validates_inputs() -> None:
    with pytest.raises(ValueError):
        s_from_s_plus(s_plus=0.0, u_tau=0.05, nu=1e-6)
    with pytest.raises(ValueError):
        s_from_s_plus(s_plus=17.0, u_tau=0.0, nu=1e-6)
    with pytest.raises(ValueError):
        s_from_s_plus(s_plus=17.0, u_tau=0.05, nu=0.0)


def test_strip_profile_rejects_zero_pitches() -> None:
    spec = BladeRibletSpec(pitch_s=1.0)
    with pytest.raises(ValueError):
        blade_strip_profile(spec, n_pitches=0)
