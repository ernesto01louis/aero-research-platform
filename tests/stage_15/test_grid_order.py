"""Stage 15 hardening — the 3-grid OBSERVED-order GCI (no CFD).

Pins the audit-driven upgrade from an *assumed* p=2.0 (2-grid, Fs=3.0) to a *measured* order
(3-grid, Fs=1.25) on the matched-condition delta: the observed order is recovered on synthetic
monotone data, oscillatory families fall back conservatively, faster-than-formal convergence is
clamped, and the triplet composes a thesis-grade GO / honest NO-GO exactly like the 2-grid path.
"""

from __future__ import annotations

import math

import pytest
from aero.optimize.report import (
    MatchedGridDeltaTriplet,
    compose_result,
    gci_3grid_fraction,
    observed_order,
)
from aero.provenance.four_fold import ProvenanceTuple

pytestmark = pytest.mark.stage_15

_R = 1.7


def _triplet_from_order(
    a: float, c: float, p: float, ratio: float = _R
) -> tuple[float, float, float]:
    """Solutions at h, r·h, r²·h for f(h) = a + c·(refinement-relative h)^p — a clean order-p family."""
    return a + c, a + c * ratio**p, a + c * ratio ** (2.0 * p)


def _prov() -> ProvenanceTuple:
    return ProvenanceTuple(
        git_sha="a" * 40,
        dvc_input_hash="0" * 64,
        container_sif_sha256="1" * 64,
        config_hash="2" * 64,
    )


def test_observed_order_recovers_known_order() -> None:
    fine, medium, coarse = _triplet_from_order(2.0, 0.02, p=1.5)
    p_obs, monotone = observed_order(fine, medium, coarse, ratio=_R)
    assert monotone is True
    assert p_obs == pytest.approx(1.5, abs=1e-9)


def test_observed_order_oscillatory_is_undefined() -> None:
    # a sign change between the two grid-to-grid differences → not asymptotic → (0.0, False)
    p_obs, monotone = observed_order(1.0, 1.1, 1.05, ratio=_R)
    assert monotone is False
    assert p_obs == 0.0


def test_gci_3grid_monotone_uses_observed_order_and_fs125() -> None:
    fine, medium, coarse = _triplet_from_order(2.0, 0.02, p=1.5)
    got = gci_3grid_fraction(fine, medium, coarse, ratio=_R)
    eps = abs(medium - fine) / abs(fine)
    expect = 1.25 * eps / (_R**1.5 - 1.0)  # Fs=1.25, measured p=1.5
    assert got == pytest.approx(expect, rel=1e-9)


def test_gci_3grid_clamps_faster_than_formal() -> None:
    # an observed order above the formal 2.0 must not be used (no faster-than-formal claim)
    fine, medium, coarse = _triplet_from_order(1.0, 0.001, p=3.0)
    assert observed_order(fine, medium, coarse, ratio=_R)[0] == pytest.approx(3.0, abs=1e-9)
    got = gci_3grid_fraction(fine, medium, coarse, ratio=_R)
    eps = abs(medium - fine) / abs(fine)
    expect = 1.25 * eps / (_R**2.0 - 1.0)  # p clamped to formal 2.0
    assert got == pytest.approx(expect, rel=1e-9)


def test_gci_3grid_oscillatory_falls_back_conservative() -> None:
    # oscillatory → first-order Fs=3.0 fallback (a non-converging family can't fake a tight band)
    fine, medium, coarse = 1.0, 1.1, 1.05
    got = gci_3grid_fraction(fine, medium, coarse, ratio=_R)
    eps = abs(medium - fine) / abs(fine)
    expect = 3.0 * eps / (_R**1.0 - 1.0)
    assert got == pytest.approx(expect, rel=1e-9)


def _delta_triplet(a: float, c: float, p: float) -> MatchedGridDeltaTriplet:
    """A grid-independent baseline (1.48) + an optimum whose DELTA has a clean order-p family."""
    df, dm, dc = _triplet_from_order(a, c, p)  # delta fine/medium/coarse
    return MatchedGridDeltaTriplet(
        quantity="lift_to_drag",
        baseline_fine=1.48,
        baseline_medium=1.48,
        baseline_coarse=1.48,
        optimum_fine=1.48 + df,
        optimum_medium=1.48 + dm,
        optimum_coarse=1.48 + dc,
        refinement_ratio=_R,
    )


def test_triplet_measures_order_and_is_significant() -> None:
    d = _delta_triplet(a=0.68, c=0.01, p=1.5)  # delta_fine = 0.69, tight convergence
    assert d.delta_fine == pytest.approx(0.69, abs=1e-9)
    assert d.delta_monotone is True
    assert d.observed_order_delta == pytest.approx(1.5, abs=1e-9)
    assert d.u95_delta_numerical < 0.05
    assert d.is_significant(higher_is_better=True, k=2.0)


def test_compose_result_triplet_go() -> None:
    result, is_go = compose_result(
        case_name="airfoil_opt_naca4",
        objective="maximize lift_to_drag (3-grid observed-order GCI)",
        quantity="lift_to_drag",
        higher_is_better=True,
        design_variables={"max_camber": 0.0745, "camber_position": 0.5926},
        delta=_delta_triplet(a=0.68, c=0.01, p=1.5),
        cfd_verified=_prov(),
        n_candidates=14,
    )
    assert is_go is True
    assert result.validation_tag == "thesis-grade"
    assert result.optimization is not None
    assert result.optimization.improvement.delta > result.optimization.improvement.required_margin


def test_compose_result_triplet_nogo_within_uncertainty() -> None:
    # a small delta with a large grid spread → within k*U95 → honest NO-GO (validated tier)
    d = MatchedGridDeltaTriplet(
        quantity="lift_to_drag",
        baseline_fine=1.48,
        baseline_medium=1.48,
        baseline_coarse=1.48,
        optimum_fine=1.50,
        optimum_medium=1.53,
        optimum_coarse=1.60,
        refinement_ratio=_R,
    )
    assert not d.is_significant(higher_is_better=True, k=2.0)
    result, is_go = compose_result(
        case_name="airfoil_opt_naca4",
        objective="o",
        quantity="lift_to_drag",
        higher_is_better=True,
        design_variables={"max_camber": 0.001},
        delta=d,
        cfd_verified=_prov(),
        n_candidates=14,
    )
    assert is_go is False
    assert result.validation_tag == "validated"
    assert result.optimization is None


def test_iterative_term_rss_into_numerical() -> None:
    # u95_delta_iterative (limit-cycle term) RSS's with the grid GCI into u95_delta_numerical.
    d0 = _delta_triplet(a=0.68, c=0.01, p=1.5)  # iterative=0 by default
    grid = d0.u95_delta_grid
    assert d0.u95_delta_numerical == pytest.approx(grid, rel=1e-12)  # no iterative -> just grid
    d1 = d0.model_copy(update={"u95_delta_iterative": 0.05})
    assert d1.u95_delta_grid == pytest.approx(grid, rel=1e-12)  # grid arm unchanged
    assert d1.u95_delta_numerical == pytest.approx((grid**2 + 0.05**2) ** 0.5, rel=1e-12)
    assert d1.u95_delta_numerical > d0.u95_delta_numerical  # iterative strictly widens the band


def test_observed_order_matches_hand_formula() -> None:
    # ln(r^p)/ln(r) == p, sanity on the closed form used above
    for p in (1.0, 1.3, 1.8, 2.0):
        fine, medium, coarse = _triplet_from_order(3.0, 0.05, p)
        assert observed_order(fine, medium, coarse, ratio=_R)[0] == pytest.approx(p, abs=1e-9)
        assert math.isclose(observed_order(fine, medium, coarse, ratio=_R)[0], p, abs_tol=1e-9)
