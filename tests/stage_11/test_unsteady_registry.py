"""Stage 11 — aero/vv/unsteady registry: case wiring, specs, metrics (host-side).

Pins that the two moving-body V&V cases register, carry the intended specs (lock-in
forcing at F=1.1, A/D=0.5; plunging foil St=0.4, h0/c=0.175), gate on the right metric +
tolerance (3% Strouhal, 15% thrust), and merge into the CLI's case table without clashing.
The reference() CSV read + the cluster GO are exercised by the slow tests in tests/vv/.
"""

from __future__ import annotations

import pytest
from aero.adapters.openfoam.cylinder import CylinderSpec
from aero.adapters.openfoam.plunging_airfoil import PlungingAirfoilSpec
from aero.vv.unsteady import UNSTEADY_CASES, OscillatingCylinderLockin, PlungingAirfoilHG2007

pytestmark = pytest.mark.stage_11


def test_both_cases_registered() -> None:
    # The Stage-11 base cases register (Stage 13 additively adds re-anchored plunging
    # variants — plunging_airfoil_hg2007_st0{2,3}[_lm] — so this is a subset check).
    assert {"oscillating_cylinder_lockin", "plunging_airfoil_hg2007"} <= set(UNSTEADY_CASES)


def test_lockin_spec_forces_above_natural() -> None:
    spec = OscillatingCylinderLockin().case_spec()
    assert isinstance(spec, CylinderSpec)
    assert spec.motion is not None
    assert spec.reynolds == 100.0
    assert spec.inflow_angle_deg == 0.0  # motion breaks symmetry; no tilt seed
    assert spec.motion.amplitude == pytest.approx(0.5)  # A/D
    assert spec.motion.frequency == pytest.approx(1.1 * 0.165)  # F = 1.1 above natural


def test_lockin_metric_is_strouhal_3pct() -> None:
    (metric,) = OscillatingCylinderLockin().metrics()
    assert metric.name == "strouhal"
    assert metric.tolerance == pytest.approx(0.03)
    assert OscillatingCylinderLockin.sweep_metric == "strouhal"


def test_plunging_spec_heathcote_gursul_conditions() -> None:
    spec = PlungingAirfoilHG2007().case_spec()
    assert isinstance(spec, PlungingAirfoilSpec)
    assert spec.reynolds == 1.0e4
    assert spec.motion.amplitude == pytest.approx(0.175)  # h0/c
    # St = 2 f h0 / U = 0.4  ->  f = 0.4 / (2*0.175)
    assert spec.motion.frequency == pytest.approx(0.4 / (2 * 0.175))


def test_plunging_metric_is_thrust_15pct() -> None:
    (metric,) = PlungingAirfoilHG2007().metrics()
    assert metric.name == "thrust_coefficient"
    assert metric.tolerance == pytest.approx(0.15)
    assert PlungingAirfoilHG2007.sweep_metric == "thrust_coefficient"


def test_refined_coarsens_mesh() -> None:
    base = OscillatingCylinderLockin().case_spec()
    coarse = OscillatingCylinderLockin().refined(1.3).case_spec()
    assert coarse.n_radial < base.n_radial
    foil_base = PlungingAirfoilHG2007().case_spec()
    foil_coarse = PlungingAirfoilHG2007().refined(1.3).case_spec()
    assert foil_coarse.n_surface < foil_base.n_surface


def test_no_name_clash_with_other_registries() -> None:
    from aero.vv.forward_regime import FORWARD_REGIME_CASES
    from aero.vv.tmr import TMR_CASES

    assert not (set(UNSTEADY_CASES) & set(FORWARD_REGIME_CASES))
    assert not (set(UNSTEADY_CASES) & set(TMR_CASES))
