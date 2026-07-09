"""Stage 14 — flapping kinematics + the tabulated6DoFMotion table generator.

Host-side: pins the WBD (2004) kinematics (ramp starts at rest, post-ramp amplitudes, the
advanced/delayed phase sign), the U_max reference speed, and the tabulated-motion table format
(identity at t=0; rotation column = the pitch deviation in degrees). Cluster correctness (the
mesh actually moving) is the slow test in tests/vv/ + the R0 moveDynamicMesh probe.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from aero.adapters.openfoam.motion import FlappingMotionSpec, flapping_motion_table
from aero.postprocess.flapping_kinematics import FlappingKinematics
from pydantic import ValidationError

pytestmark = pytest.mark.stage_14


def _motion(phase: float = 0.0, ramp: float = 1.0) -> FlappingMotionSpec:
    return FlappingMotionSpec(
        stroke_amplitude=1.4,
        frequency=1.0 / (math.pi * 2.8),  # U_max = omega*A0/2 = 1
        pitch_amplitude_deg=45.0,
        pitch_phase_deg=phase,
        pitch_mean_deg=90.0,
        ramp_cycles=ramp,
    )


def test_u_ref_is_max_wing_speed() -> None:
    m = _motion()
    # U_max = omega * stroke_amplitude = pi f A0. With A0/2=1.4, f=1/(pi*2.8): U_max = 1.
    assert m.u_ref == pytest.approx(1.0)
    assert m.period == pytest.approx(1.0 / m.frequency)


def test_ramp_starts_at_rest() -> None:
    m = _motion(ramp=1.0)
    kin = m.kinematics.evaluate(np.array([0.0, 1.0e-7]))
    assert abs(kin["stroke_pos"][0]) < 1e-12
    assert abs(kin["stroke_vel"][0]) < 1e-8  # zero initial LINEAR velocity
    assert abs(kin["pitch_dev_deg"][0]) < 1e-12  # zero initial rotation


def test_post_ramp_reaches_full_amplitude() -> None:
    m = _motion(ramp=1.0)
    t = np.linspace(0.0, 8.0 * m.period, 20000)
    kin = m.kinematics.evaluate(t)
    post = t > 3.0 * m.period
    assert kin["stroke_pos"][post].max() == pytest.approx(1.4, rel=1e-3)
    assert kin["pitch_dev_deg"][post].max() == pytest.approx(45.0, rel=1e-3)
    # peak wing speed == U_max at full amplitude
    assert kin["speed"][post].max() == pytest.approx(m.u_ref, rel=1e-2)


def test_no_ramp_starts_at_stroke_extreme() -> None:
    m = _motion(ramp=0.0)
    kin = m.kinematics.evaluate(np.array([0.0]))
    # s(0) = A cos(0) = A (the stroke extreme), velocity 0 there.
    assert kin["stroke_pos"][0] == pytest.approx(1.4)
    assert abs(kin["stroke_vel"][0]) < 1e-9


def test_rotation_timing_phase_sign() -> None:
    # At the stroke reversal (t=0, no ramp) advanced rotation has ALREADY rotated the wing
    # (dev > 0) while delayed rotation has not yet (dev < 0) — exact mirror images there:
    # dev = beta*sin(+/-45 deg) = +/- beta/sqrt(2).
    adv = _motion(phase=45.0, ramp=0.0).kinematics.evaluate(np.array([0.0]))
    dly = _motion(phase=-45.0, ramp=0.0).kinematics.evaluate(np.array([0.0]))
    assert adv["pitch_dev_deg"][0] == pytest.approx(45.0 / math.sqrt(2.0))
    assert dly["pitch_dev_deg"][0] == pytest.approx(-45.0 / math.sqrt(2.0))


def test_pure_kinematics_matches_spec() -> None:
    m = _motion(phase=30.0)
    k = m.kinematics
    assert isinstance(k, FlappingKinematics)
    assert k.pitch_phase_deg == 30.0 and k.stroke_amplitude == 1.4


def test_motion_table_identity_at_start_and_rotation_column() -> None:
    m = _motion(ramp=1.0)
    tab = flapping_motion_table(m, end_time=2.0 * m.period, samples_per_cycle=64)
    lines = [ln.strip() for ln in tab.splitlines() if ln.strip()]
    n_declared = int(lines[0])
    rows = [ln for ln in lines if ln.startswith("(") and "((" in ln]
    assert len(rows) == n_declared  # header count matches the number of data rows
    # First data row is the identity transform (zero translation, zero rotation).
    assert rows[0].startswith("(0 ((0 0 0) (0 0 0)))")
    # Every row's z-rotation equals the analytic pitch deviation at that time (deg).
    t = np.linspace(0.0, 2.0 * m.period, n_declared)
    dev = m.kinematics.evaluate(t)["pitch_dev_deg"]
    import re

    for row, expected in zip(rows, dev, strict=True):
        rot_z = float(re.findall(r"\(0 0 ([-0-9.eE+]+)\)", row)[0])
        assert rot_z == pytest.approx(float(expected), abs=1e-6)


def test_frozen_and_strict() -> None:
    m = _motion()
    with pytest.raises(ValidationError):
        FlappingMotionSpec(stroke_amplitude=1.0, frequency=1.0, pitch_amplitude_deg=1.0, bogus=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        m.stroke_amplitude = 2.0  # frozen


def test_negative_stroke_amplitude_rejected() -> None:
    with pytest.raises(ValidationError):
        FlappingMotionSpec(stroke_amplitude=-1.0, frequency=1.0, pitch_amplitude_deg=45.0)
