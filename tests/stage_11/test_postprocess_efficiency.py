"""Stage 11 — aero.postprocess.efficiency (thrust / power / propulsive efficiency).

Uses an analytic force field so the metrics have closed-form values:
* F_x = -T0 (constant) -> thrust T0, so C_T = T0 / (0.5 rho U^2 A).
* F_y = -c * ydot -> P_in = c * <ydot^2>, so C_P and eta follow in closed form.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from aero.postprocess import MotionKinematics, Signal, propulsive_metrics

pytestmark = pytest.mark.stage_11


def test_motion_kinematics_velocity_and_zero_at_extrema() -> None:
    kin = MotionKinematics(amplitude=1.0, omega=2 * math.pi)
    assert kin.period == pytest.approx(1.0)
    # displacement y = sin(2pi t): at t=0.25 y=1 (extreme), velocity=0.
    assert float(kin.displacement(np.array([0.25]))[0]) == pytest.approx(1.0, abs=1e-9)
    assert float(kin.velocity(np.array([0.25]))[0]) == pytest.approx(0.0, abs=1e-9)


def test_propulsive_metrics_closed_form() -> None:
    kin = MotionKinematics(amplitude=1.0, omega=2 * math.pi)  # period 1, f=1
    t = np.linspace(0.0, 5.0, 5 * 400 + 1)  # 5 full periods
    ydot = kin.velocity(t)  # = 2pi cos(2pi t)
    fx = Signal.from_arrays(t, np.full_like(t, -0.5), name="fx")  # thrust 0.5
    fy = Signal.from_arrays(t, -0.5 * ydot, name="fy")  # F_y = -0.5*ydot

    m = propulsive_metrics(fx=fx, fy=fy, kin=kin, rho=1.0, u_inf=1.0, ref_area=1.0)
    # q = 0.5; C_T = 0.5/0.5 = 1.0
    assert m.thrust_coefficient == pytest.approx(1.0, rel=1e-3)
    # P_in = 0.5*<ydot^2> = 0.5 * (2pi)^2 * 0.5 = pi^2 ; C_P = pi^2/(0.5) = 2 pi^2
    assert m.power_coefficient == pytest.approx(2 * math.pi**2, rel=1e-3)
    assert m.propulsive_efficiency == pytest.approx(1.0 / (2 * math.pi**2), rel=1e-3)
    assert m.strouhal == pytest.approx(2.0, rel=1e-9)  # 2 f h0 / U = 2*1*1/1
    assert m.n_cycles == 5


def test_propulsive_efficiency_none_when_net_drag() -> None:
    kin = MotionKinematics(amplitude=1.0, omega=2 * math.pi)
    t = np.linspace(0.0, 5.0, 5 * 400 + 1)
    ydot = kin.velocity(t)
    fx = Signal.from_arrays(t, np.full_like(t, +0.5), name="fx")  # net DRAG (F_x > 0)
    fy = Signal.from_arrays(t, -0.5 * ydot, name="fy")
    m = propulsive_metrics(fx=fx, fy=fy, kin=kin, rho=1.0, u_inf=1.0, ref_area=1.0)
    assert m.thrust_coefficient < 0.0
    assert m.propulsive_efficiency is None  # undefined below the net-thrust threshold


def test_propulsive_metrics_requires_matched_time_base() -> None:
    kin = MotionKinematics(amplitude=1.0, omega=2 * math.pi)
    t1 = np.linspace(0.0, 5.0, 2001)
    t2 = np.linspace(0.0, 5.0, 2001) + 0.001
    fx = Signal.from_arrays(t1, np.full_like(t1, -0.5), name="fx")
    fy = Signal.from_arrays(t2, np.full_like(t2, 0.1), name="fy")
    with pytest.raises(ValueError, match="same time base"):
        propulsive_metrics(fx=fx, fy=fy, kin=kin, rho=1.0, u_inf=1.0, ref_area=1.0)
