"""Stage 05 unit tests for the ASME V&V 20 grid-convergence index — pure math.

The reference numbers are the worked example from Celik et al. (2008),
"Procedure for Estimation and Reporting of Uncertainty Due to Discretization
in CFD Applications" (J. Fluids Eng. 130(7)) — sample calculation 1.
"""

from __future__ import annotations

import pytest
from aero.vv import BenchmarkError
from aero.vv.mesh_sweep import GridPoint, grid_convergence_index

pytestmark = pytest.mark.stage_05


def _grids(
    h: tuple[float, float, float], phi: tuple[float, float, float]
) -> tuple[GridPoint, GridPoint, GridPoint]:
    return tuple(  # type: ignore[return-value]
        GridPoint(
            refinement_ratio=1.0 + i * 0.3,
            n_cells=10_000 - i * 3_000,
            representative_h=h[i],
            metric_value=phi[i],
        )
        for i in range(3)
    )


def test_gci_matches_celik_worked_example() -> None:
    # Celik et al. (2008): r21 = 1.5, r32 = 1.333; phi = 6.063, 5.972, 5.863.
    grids = _grids((1.0, 1.5, 2.0), (6.063, 5.972, 5.863))
    p, extrapolated, gci_fine, monotonic = grid_convergence_index(grids)
    assert monotonic
    assert p == pytest.approx(1.53, abs=0.03)
    assert extrapolated == pytest.approx(6.1685, abs=0.01)
    assert gci_fine * 100.0 == pytest.approx(2.17, abs=0.1)


def test_gci_flags_oscillatory_convergence() -> None:
    # phi swings 5.0 -> 5.2 -> 5.05: successive differences flip sign.
    grids = _grids((1.0, 1.5, 2.0), (5.0, 5.2, 5.05))
    _p, _ext, _gci, monotonic = grid_convergence_index(grids)
    assert monotonic is False


def test_gci_rejects_non_ordered_grids() -> None:
    grids = _grids((2.0, 1.5, 1.0), (6.063, 5.972, 5.863))  # coarse-first
    with pytest.raises(BenchmarkError, match="fine -> coarse"):
        grid_convergence_index(grids)


def test_gci_rejects_identical_fine_grids() -> None:
    grids = _grids((1.0, 1.5, 2.0), (6.0, 6.0, 5.8))  # phi1 == phi2
    with pytest.raises(BenchmarkError, match="identical"):
        grid_convergence_index(grids)
