"""Stage 14 — the flapping-wing loader (_load_flapping) on a synthetic force history.

Drives the REAL OpenFOAMSolver().load() over a hand-written dimensional `forces` FO file (the
Stage-11 synthetic-postProcessing idiom), so the whole WBD-normalisation + cycle-convergence +
stroke-averaging path is exercised with zero CFD. Asserts the recovered mean lift coefficient,
and the FAIL-LOUD non-convergence path (the NO-GO discipline).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from aero.adapters._base import CaseDir, ResultHandle
from aero.adapters.openfoam._foam_common import RHO_INF
from aero.adapters.openfoam.flapping_wing import FlappingWingSpec
from aero.adapters.openfoam.motion import FlappingMotionSpec
from aero.adapters.openfoam.solver import OpenFOAMSolver
from aero.postprocess.flapping_forces import wbd_quasi_steady_normalisers

pytestmark = pytest.mark.stage_14


def _spec() -> FlappingWingSpec:
    return FlappingWingSpec(
        name="wbd_test",
        reynolds=75.0,
        motion=FlappingMotionSpec(
            stroke_amplitude=1.4,
            frequency=1.0 / (math.pi * 2.8),
            pitch_amplitude_deg=45.0,
            pitch_mean_deg=90.0,
            ramp_cycles=0.0,  # synthetic data is "already converged"
        ),
        n_radial=40,
        n_azimuthal=24,
        end_time_cycles=16.0,
    )


def _write_forces(
    tmp_path: Path, spec: FlappingWingSpec, *, mean_fy: float, drift: float = 0.0
) -> ResultHandle:
    """Write a synthetic `forces` FO history: vertical force with a known per-cycle mean.

    ``drift`` (per cycle, fractional) makes the mean walk so the convergence detector fails.
    """
    m = spec.motion
    omega = m.omega
    period = m.period
    t = np.arange(0.0, 16.0 * period, period / 60.0)
    ncyc = t / period
    fy = mean_fy * (1.0 + drift * ncyc) + 0.2 * mean_fy * np.sin(omega * t)
    fx = np.zeros_like(t)  # drag is diagnostic; keep the vertical force clean
    post = tmp_path / "postProcessing"
    fd = post / "forces1" / "0"
    fd.mkdir(parents=True)
    rows = [
        f"{ti:.8g} (({fxi:.8g} {fyi:.8g} 0) (0 0 0) (0 0 0)) ((0 0 0)(0 0 0)(0 0 0))"
        for ti, fxi, fyi in zip(t, fx, fy, strict=True)
    ]
    (fd / "force.dat").write_text("\n".join(rows) + "\n")
    case_dir = CaseDir(run_id="flap1", spec=spec, host_path=tmp_path, remote_path=Path("/case"))
    return ResultHandle(case_dir=case_dir, returncode=0, output_host_path=post)


def test_load_flapping_recovers_mean_lift_coefficient(tmp_path: Path) -> None:
    spec = _spec()
    # Choose the dimensional vertical force so the WBD-normalised mean C_L is a known 0.80.
    n_l, _ = wbd_quasi_steady_normalisers(
        spec.motion.kinematics, rho=RHO_INF, chord=spec.chord, span=spec.span
    )
    target_cl = 0.80
    mean_fy = target_cl * n_l
    solve = OpenFOAMSolver().load(_write_forces(tmp_path, spec, mean_fy=mean_fy))
    assert solve.scalars["cycle_converged"] == 1.0
    assert solve.scalars["mean_lift_coefficient"] == pytest.approx(target_cl, rel=2e-2)
    assert solve.cl == pytest.approx(target_cl, rel=2e-2)
    assert solve.scalars["n_converged_cycles"] >= 4
    assert solve.scalars["wbd_norm_lift"] == pytest.approx(n_l, rel=1e-9)
    assert solve.history.monitor_name == "lift_coefficient"


def test_load_flapping_fails_loud_on_non_convergence(tmp_path: Path) -> None:
    spec = _spec()
    n_l, _ = wbd_quasi_steady_normalisers(
        spec.motion.kinematics, rho=RHO_INF, chord=spec.chord, span=spec.span
    )
    # A steadily growing mean lift never reaches a periodic steady state -> NO-GO, fail loud.
    handle = _write_forces(tmp_path, spec, mean_fy=0.5 * n_l, drift=0.05)
    with pytest.raises(ValueError, match="periodic steady state"):
        OpenFOAMSolver().load(handle)


def test_flapping_force_trace_is_reusable(tmp_path: Path) -> None:
    spec = _spec()
    n_l, _ = wbd_quasi_steady_normalisers(
        spec.motion.kinematics, rho=RHO_INF, chord=spec.chord, span=spec.span
    )
    handle = _write_forces(tmp_path, spec, mean_fy=0.8 * n_l)
    trace = OpenFOAMSolver().flapping_force_trace(handle)
    assert len(trace.cl) == len(trace.t) > 100
    assert trace.n_l == pytest.approx(n_l, rel=1e-9)
    assert trace.u_ref == pytest.approx(spec.motion.u_ref)
