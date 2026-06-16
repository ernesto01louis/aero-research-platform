"""Stage 10 — transient cylinder Strouhal (host-side).

Pins the transient/FFT machinery: the cylinder case is a transient (pimpleFoam)
laminar case, the O-grid generates, the FFT helper recovers a known shedding
frequency to sub-bin accuracy, and the case wiring. The cluster St check is the
slow test in tests/vv/test_forward_regime_cylinder.py.
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.adapters.openfoam.cylinder import write_cylinder_case
from aero.adapters.openfoam.solver import _strouhal_from_signal
from aero.vv.forward_regime import FORWARD_REGIME_CASES, CylinderStrouhal

pytestmark = pytest.mark.stage_10


def test_fft_recovers_known_strouhal() -> None:
    # A clean shedding signal at St=0.165 (D=U=1) + mean offset + harmonic noise;
    # parabolic peak interpolation should recover it to well under 1%.
    t = np.linspace(0.0, 120.0, 600)
    cl = 0.3 * np.sin(2 * np.pi * 0.165 * t) + 0.12 + 0.02 * np.cos(2 * np.pi * 0.33 * t)
    st = _strouhal_from_signal(t, cl, diameter=1.0, u_inf=1.0)
    assert st == pytest.approx(0.165, abs=0.003)


def test_case_is_registered_transient_laminar() -> None:
    assert "cylinder_strouhal_re100" in FORWARD_REGIME_CASES
    spec = CylinderStrouhal().case_spec()
    assert spec.transient is True
    assert spec.turbulence_model == "laminar"
    assert spec.reynolds == 100.0
    assert spec.inflow_angle_deg > 0.0  # shedding seed


def test_case_generates_transient_pimplefoam_ogrid(tmp_path) -> None:
    write_cylinder_case(CylinderStrouhal().case_spec(), tmp_path)
    cd = (tmp_path / "system" / "controlDict").read_text()
    assert "application     pimpleFoam;" in cd
    assert "adjustTimeStep  yes;" in cd
    bm = (tmp_path / "system" / "blockMeshDict").read_text()
    assert bm.count("hex (") == 4  # 4-block O-grid
    assert bm.count("arc ") == 16  # inner+outer arcs, z=0 + z=span
    fv = (tmp_path / "system" / "fvSolution").read_text()
    assert "PIMPLE" in fv
    zero = sorted(p.name for p in (tmp_path / "0").iterdir())
    assert zero == ["U", "p"]  # laminar


def test_metric_is_strouhal_5pct() -> None:
    (metric,) = CylinderStrouhal().metrics()
    assert metric.name == "strouhal"
    assert metric.tolerance == pytest.approx(0.05)
