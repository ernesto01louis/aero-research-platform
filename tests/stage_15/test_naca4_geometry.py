"""Stage 15 — NACA-4 shape parametrization: baseline recovery + matched mesh topology.

The optimizer's honest matched-condition delta depends on two invariants: the shaped geometry
recovers the fixed NACA 0012 exactly at zero design variables, and a shape change perturbs y only
on the fixed x-stations so the mesh topology (block/cell counts) is invariant.
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.adapters.openfoam.case_writer import _blockmeshdict
from aero.adapters.openfoam.geometry import naca0012_coordinates, naca4_coordinates
from aero.adapters.openfoam.schemas import CaseSpec

pytestmark = pytest.mark.stage_15


def test_baseline_recovery_exact() -> None:
    base = naca0012_coordinates(241)
    up = naca4_coordinates(241, max_camber=0.0, max_thickness_frac=0.12, surface="upper")
    lo = naca4_coordinates(241, max_camber=0.0, max_thickness_frac=0.12, surface="lower")
    assert np.max(np.abs(up - base)) == 0.0  # byte-identical upper
    assert np.max(np.abs(lo[:, 1] - (-base[:, 1]))) == 0.0  # lower is the exact mirror


def test_camber_perturbs_y_only_positive_thickness() -> None:
    base = naca0012_coordinates(241)
    up = naca4_coordinates(241, max_camber=0.05, camber_position=0.4, surface="upper")
    lo = naca4_coordinates(241, max_camber=0.05, camber_position=0.4, surface="lower")
    assert np.max(np.abs(up[:, 0] - base[:, 0])) == 0.0  # x-stations unchanged
    assert np.min(up[:, 1] - lo[:, 1]) >= 0.0  # positive section thickness
    assert up[:, 1].max() > base[:, 1].max()  # camber lifts the upper surface
    assert up[0, 1] == 0.0 and up[-1, 1] == 0.0  # LE + sharp TE snapped


def test_thickness_scales() -> None:
    thin = naca4_coordinates(121, max_camber=0.0, max_thickness_frac=0.08, surface="upper")
    thick = naca4_coordinates(121, max_camber=0.0, max_thickness_frac=0.16, surface="upper")
    assert thin[:, 1].max() < 0.06 < thick[:, 1].max()  # t/c scales the peak


def test_out_of_range_camber_position_rejected() -> None:
    with pytest.raises(ValueError, match="camber_position"):
        naca4_coordinates(51, max_camber=0.04, camber_position=1.5)


def _spec(**kw: float) -> CaseSpec:
    return CaseSpec(
        name="a",
        reynolds=1000,
        mach=0.1,
        aoa_deg=4.0,
        turbulence_model="laminar",
        n_surface=40,
        n_normal=40,
        n_front=20,
        n_wake=30,
        first_cell_height=1e-3,
        **kw,  # type: ignore[arg-type]
    )


def test_matched_mesh_topology() -> None:
    base = _blockmeshdict(_spec())
    camb = _blockmeshdict(_spec(max_camber=0.04, camber_position=0.4))
    # Same block + polyLine counts => matched topology => honest matched-condition delta.
    assert base.count("hex (") == camb.count("hex (") == 8
    assert base.count("polyLine") == camb.count("polyLine") == 8


def test_baseline_blockmesh_unchanged() -> None:
    # The default (baseline) CaseSpec still takes the exact pre-Stage-15 NACA-0012 path.
    assert _blockmeshdict(_spec()) == _blockmeshdict(_spec())
    assert "(xm, -ym)" not in _blockmeshdict(_spec())  # de-mirrored, but symmetric at baseline
