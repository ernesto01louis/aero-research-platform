"""Stage 14 — FLAPPING_CASES registry + reference wiring (host-side).

Pins the three rotation-timing variants, their pitch-phase mapping, the experiment-anchored
reference lookup, the refined/refined_dt round-trips, and that the flapping names do not collide
with the other V&V tiers.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.vv.ercoftac import ERCOFTAC_CASES
from aero.vv.flapping import FLAPPING_CASES, FlappingWingWBD2004
from aero.vv.unsteady import UNSTEADY_CASES

pytestmark = pytest.mark.stage_14

_REPO = Path(__file__).resolve().parents[2]


def test_three_rotation_timing_variants() -> None:
    assert set(FLAPPING_CASES) == {
        "flapping_wing_wbd2004",
        "flapping_wing_wbd2004_advanced",
        "flapping_wing_wbd2004_delayed",
    }


def test_symmetrical_is_the_base_gated_case() -> None:
    sym = FLAPPING_CASES["flapping_wing_wbd2004"]
    assert sym.case_spec().motion.pitch_phase_deg == 0.0
    assert sym.sweep_metric == "mean_lift_coefficient"
    m = sym.metrics()
    assert len(m) == 1 and m[0].name == "mean_lift_coefficient"
    assert m[0].kind == "scalar" and m[0].comparison == "relative"


@pytest.mark.parametrize(
    ("name", "phase"),
    [
        ("flapping_wing_wbd2004", 0.0),
        ("flapping_wing_wbd2004_advanced", 45.0),
        ("flapping_wing_wbd2004_delayed", -45.0),
    ],
)
def test_variant_phase_mapping(name: str, phase: float) -> None:
    assert FLAPPING_CASES[name].case_spec().motion.pitch_phase_deg == phase


@pytest.mark.parametrize(
    ("name", "cl_exp"),
    [
        ("flapping_wing_wbd2004", 0.86),
        ("flapping_wing_wbd2004_advanced", 0.93),
        ("flapping_wing_wbd2004_delayed", 0.38),
    ],
)
def test_reference_anchors_to_experiment(name: str, cl_exp: float) -> None:
    ref = FLAPPING_CASES[name].reference(_REPO)
    assert ref.scalars["mean_lift_coefficient"] == pytest.approx(cl_exp)


def test_refined_scales_mesh_counts() -> None:
    sym = FLAPPING_CASES["flapping_wing_wbd2004"]
    base = sym.case_spec()
    r = sym.refined(1.5)
    assert r.case_spec().n_radial < base.n_radial
    assert r.case_spec().n_azimuthal < base.n_azimuthal
    # round-trips to the same case type and timing
    assert isinstance(r, FlappingWingWBD2004)
    assert r.case_spec().motion.pitch_phase_deg == base.motion.pitch_phase_deg


def test_refined_dt_scales_courant_only() -> None:
    sym = FLAPPING_CASES["flapping_wing_wbd2004"]
    base = sym.case_spec()
    rt = sym.refined_dt(2.0)
    assert rt.case_spec().max_courant == pytest.approx(base.max_courant * 2.0)
    assert rt.case_spec().n_radial == base.n_radial  # mesh unchanged
    with pytest.raises(ValueError, match="ratio"):
        sym.refined_dt(0.0)


def test_no_name_collision_across_tiers() -> None:
    for name in FLAPPING_CASES:
        assert name not in UNSTEADY_CASES
        assert name not in ERCOFTAC_CASES
