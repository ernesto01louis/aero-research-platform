"""Stage 16 — the hard GO gates: significance alone is NOT a GO.

The Stage-15 driver recorded `all_converged` but composed the verdict unconditionally, so a
huge delta measured on a non-converged or non-asymptotic family could read as GO. The gates
close that gap: GO requires significance AND every claim solve converged AND a monotone delta
AND an observed order inside `[min_order, formal_order]`. A demotion never relaxes k.
"""

from __future__ import annotations

import pytest
from aero.optimize.report import MatchedGridDeltaTriplet, certification_gates

pytestmark = pytest.mark.stage_16

_RATIO = 1.7


def _triplet(
    deltas: tuple[float, float, float], *, baseline: float = 10.0, u95_iter: float = 0.0
) -> MatchedGridDeltaTriplet:
    """Baseline pinned per grid so the delta series is exactly `deltas` (fine, medium, coarse)."""
    return MatchedGridDeltaTriplet(
        quantity="lift_to_drag",
        baseline_fine=baseline,
        baseline_medium=baseline,
        baseline_coarse=baseline,
        optimum_fine=baseline + deltas[0],
        optimum_medium=baseline + deltas[1],
        optimum_coarse=baseline + deltas[2],
        refinement_ratio=_RATIO,
        u95_delta_iterative=u95_iter,
    )


def _monotone_deltas(
    p: float, *, fine: float = 24.0, e21: float = 0.5
) -> tuple[float, float, float]:
    """A delta series converging monotonically at observed order p (e32/e21 = ratio**p)."""
    e32 = e21 * _RATIO**p
    return (fine, fine + e21, fine + e21 + e32)


def test_clean_family_passes_all_gates() -> None:
    trip = _triplet(_monotone_deltas(1.5))
    gates = certification_gates(trip, all_converged=True, higher_is_better=True)
    assert gates == {
        "significant": True,
        "all_converged": True,
        "delta_monotone": True,
        "order_in_asymptotic_range": True,
    }
    assert all(gates.values())


def test_unconverged_solve_demotes_even_when_significant() -> None:
    trip = _triplet(_monotone_deltas(1.5))
    assert trip.is_significant(higher_is_better=True)  # the Stage-15 trap: significant but...
    gates = certification_gates(trip, all_converged=False, higher_is_better=True)
    assert not gates["all_converged"] and not all(gates.values())


def test_oscillatory_delta_fails_monotone_and_order_gates() -> None:
    trip = _triplet((24.0, 23.0, 24.5))  # sign-flipping error series
    gates = certification_gates(trip, all_converged=True, higher_is_better=True)
    assert not gates["delta_monotone"]
    assert not gates["order_in_asymptotic_range"]
    assert not all(gates.values())


def test_order_below_asymptotic_range_demotes() -> None:
    trip = _triplet(_monotone_deltas(0.3, e21=1.0))
    gates = certification_gates(trip, all_converged=True, higher_is_better=True)
    assert gates["delta_monotone"]
    assert not gates["order_in_asymptotic_range"]


def test_order_above_formal_demotes() -> None:
    # Faster-than-formal observed order = pre-asymptotic coincidence, not superconvergence.
    trip = _triplet(_monotone_deltas(3.0, e21=0.2))
    gates = certification_gates(trip, all_converged=True, higher_is_better=True)
    assert gates["delta_monotone"]
    assert trip.observed_order_delta > trip.formal_order
    assert not gates["order_in_asymptotic_range"]


def test_insignificant_delta_fails_significance_gate() -> None:
    trip = _triplet(_monotone_deltas(1.5, fine=0.5), u95_iter=5.0)  # delta buried in U95
    gates = certification_gates(trip, all_converged=True, higher_is_better=True)
    assert not gates["significant"]
    assert gates["delta_monotone"] and gates["order_in_asymptotic_range"]
