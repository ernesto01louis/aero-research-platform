"""Stage 10 — forward-regime Blasius laminar flat plate (host-side).

Pins the laminar solve path (the case generates a `simulationType laminar`
OpenFOAM case with only U and p — no k/omega/nut), the analytical Blasius
reference, and the case wiring. The cluster Cf-vs-Blasius check is the slow
test in tests/vv/test_forward_regime_blasius.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.tmr_case_writer import write_tmr_case
from aero.vv.forward_regime import FORWARD_REGIME_CASES, BlasiusFlatPlate
from aero.vv.forward_regime.blasius_flat_plate import blasius_cf

pytestmark = pytest.mark.stage_10

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_blasius_cf_formula() -> None:
    # Cf = 0.664/sqrt(Re_x), Re_x = Re_L * x / L. At x=L, Re_x = Re_L.
    assert blasius_cf(2.0, reynolds=1.0e5, plate_length=2.0) == pytest.approx(0.664 / 1.0e5**0.5)
    # Halving x raises Cf by sqrt(2).
    cf1 = blasius_cf(1.0, reynolds=1.0e5, plate_length=2.0)
    cf05 = blasius_cf(0.5, reynolds=1.0e5, plate_length=2.0)
    assert cf05 / cf1 == pytest.approx(2.0**0.5)
    with pytest.raises(ValueError, match="singular"):
        blasius_cf(0.0, reynolds=1.0e5, plate_length=2.0)


def test_case_is_registered_and_laminar() -> None:
    assert "blasius_flat_plate" in FORWARD_REGIME_CASES
    spec = BlasiusFlatPlate().case_spec()
    assert spec.turbulence_model == "laminar"
    assert spec.reynolds == 1.0e5  # sub-transition over the whole plate


def test_case_generates_a_laminar_openfoam_case(tmp_path: Path) -> None:
    write_tmr_case(BlasiusFlatPlate().case_spec(), tmp_path)
    # laminar => only U and p in 0/, and simulationType laminar.
    zero_fields = sorted(p.name for p in (tmp_path / "0").iterdir())
    assert zero_fields == ["U", "p"]
    tp = (tmp_path / "constant" / "turbulenceProperties").read_text()
    assert "simulationType  laminar;" in tp
    assert "RASModel" not in tp


def test_metric_is_cf_pointwise_5pct() -> None:
    (metric,) = BlasiusFlatPlate().metrics()
    assert metric.name == "cf"
    assert metric.kind == "pointwise"
    assert metric.tolerance == pytest.approx(0.05)


def test_reference_matches_the_blasius_law() -> None:
    ref = BlasiusFlatPlate().reference(_REPO_ROOT)
    cf = ref.series["cf"]
    spec = BlasiusFlatPlate().case_spec()
    # every tabulated reference point equals the analytical law it documents.
    for x, y in zip(cf.x, cf.y, strict=True):
        assert y == pytest.approx(
            blasius_cf(x, reynolds=spec.reynolds, plate_length=spec.plate_length), rel=1e-4
        )


def test_refined_scales_and_stays_laminar() -> None:
    coarse = BlasiusFlatPlate().refined(2.0).case_spec()
    base = BlasiusFlatPlate().case_spec()
    assert coarse.n_streamwise < base.n_streamwise
    assert coarse.turbulence_model == "laminar"  # refinement preserves the laminar solve
