"""Stage-12 combined space+time GCI seams on the moving cylinder.

``refined()`` scales the mesh at fixed Courant (the spatial GCI arm); ``refined_dt()`` scales the
Courant-driven timestep at fixed mesh (the temporal GCI arm). Host-fast, no cluster.
"""

from __future__ import annotations

import pytest
from aero.vv.unsteady import OscillatingCylinderLockin

pytestmark = pytest.mark.stage_12


def test_refined_scales_mesh_not_timestep() -> None:
    base = OscillatingCylinderLockin()
    b = base.case_spec()
    coarse = base.refined(1.7).case_spec()
    assert coarse.n_radial < b.n_radial
    assert coarse.n_azimuthal < b.n_azimuthal
    assert coarse.max_courant == b.max_courant  # mesh refinement leaves the timestep alone


def test_refined_dt_scales_timestep_not_mesh() -> None:
    base = OscillatingCylinderLockin()
    b = base.case_spec()
    coarse_dt = base.refined_dt(2.0).case_spec()
    assert coarse_dt.max_courant == 2.0 * b.max_courant  # coarser (larger Courant cap)
    assert coarse_dt.n_radial == b.n_radial  # fixed mesh
    assert coarse_dt.n_azimuthal == b.n_azimuthal


def test_refined_dt_rejects_nonpositive() -> None:
    with pytest.raises(ValueError, match="ratio must be > 0"):
        OscillatingCylinderLockin().refined_dt(0.0)
