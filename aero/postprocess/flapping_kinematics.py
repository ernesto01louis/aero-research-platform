"""Prescribed 2-D flapping-wing kinematics (Wang, Birch & Dickinson 2004).

The pure, solver-agnostic kinematics object — the counterpart of
:class:`aero.postprocess.efficiency.MotionKinematics` for a combined translation + pitch
stroke. It is the **single source of truth** for the wing's motion: the OpenFOAM
``tabulated6DoFMotion`` table writer (:mod:`aero.adapters.openfoam.motion`) and the force
normaliser (:mod:`aero.postprocess.flapping_forces`) both evaluate it, so the mesh motion and
the coefficient definitions can never drift apart.

Kinematics (WBD Eqs 10-11), with ``stroke_amplitude = A0/2``::

    stroke:  s(t) = stroke_amplitude * cos(omega t)
    pitch:   alpha(t) = pitch_mean_deg + pitch_amplitude_deg * sin(omega t + pitch_phase_deg)

Both oscillatory parts are multiplied by a C1 startup envelope over ``ramp_cycles`` so the
wing begins from rest at mid-stroke (zero initial linear AND angular velocity — the fix for
the impulsive-start SIGFPE that killed the fine plunging mesh in Stage 13). The post-ramp
limit cycle is independent of the ramp.

stdlib + numpy + pydantic only.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel, Field

from aero.postprocess._base import _STRICT


class FlappingKinematics(BaseModel):
    """Prescribed sinusoidal translation + sinusoidal pitch about a pivot (WBD 2004)."""

    model_config = _STRICT

    stroke_amplitude: float = Field(
        ..., gt=0.0, description="Stroke half-amplitude A0/2 (pivot translation, length units)."
    )
    frequency: float = Field(..., gt=0.0, description="Flapping frequency f (1/time).")
    pitch_amplitude_deg: float = Field(
        ...,
        ge=0.0,
        description="Pitch amplitude beta about the pivot (deg); 0 => pure translation.",
    )
    pitch_phase_deg: float = Field(
        default=0.0,
        description="Rotation timing phi (deg): 0 symmetrical, >0 advanced, <0 delayed.",
    )
    pitch_mean_deg: float = Field(
        default=90.0, description="Mid-stroke wing-chord angle alpha0 vs the stroke axis (deg)."
    )
    stroke_plane_deg: float = Field(
        default=0.0, description="Inclination of the stroke line vs +x (deg); 0 = horizontal."
    )
    ramp_cycles: float = Field(
        default=1.0, ge=0.0, description="C1 (1-cos) startup-ramp length in cycles; 0 = no ramp."
    )

    @property
    def omega(self) -> float:
        """Angular frequency ``2 pi f`` (rad/time)."""
        return 2.0 * math.pi * self.frequency

    @property
    def period(self) -> float:
        """Flapping period ``1 / f``."""
        return 1.0 / self.frequency

    @property
    def u_ref(self) -> float:
        """Maximum wing speed ``U_max = omega * stroke_amplitude = pi f A0`` (WBD reference)."""
        return self.omega * self.stroke_amplitude

    def envelope(self, t: np.ndarray) -> np.ndarray:
        """C1 startup envelope e(t) in [0,1]: ``0.5(1-cos(pi t/(R T)))`` for t<R T, else 1."""
        t = np.asarray(t, dtype=np.float64)
        if self.ramp_cycles <= 0.0:
            return np.ones_like(t)
        ramp_time = self.ramp_cycles * self.period
        x = np.clip(t / ramp_time, 0.0, 1.0)
        return 0.5 * (1.0 - np.cos(math.pi * x))

    def _envelope_rate(self, t: np.ndarray) -> np.ndarray:
        """de/dt of the startup envelope (0 outside the ramp and at both ends)."""
        t = np.asarray(t, dtype=np.float64)
        if self.ramp_cycles <= 0.0:
            return np.zeros_like(t)
        ramp_time = self.ramp_cycles * self.period
        inside = t < ramp_time
        de = np.zeros_like(t)
        de[inside] = 0.5 * (math.pi / ramp_time) * np.sin(math.pi * t[inside] / ramp_time)
        return de

    def evaluate(self, t: np.ndarray) -> dict[str, np.ndarray]:
        """Analytic kinematics on a time grid (see module docstring for the returned keys)."""
        t = np.asarray(t, dtype=np.float64)
        w = self.omega
        e = self.envelope(t)
        de = self._envelope_rate(t)

        a = self.stroke_amplitude
        stroke_pos = a * e * np.cos(w * t)
        stroke_vel = a * (de * np.cos(w * t) - e * w * np.sin(w * t))

        sp = math.radians(self.stroke_plane_deg)
        cx, cy = math.cos(sp), math.sin(sp)

        beta = self.pitch_amplitude_deg
        phi = math.radians(self.pitch_phase_deg)
        pitch_dev_deg = beta * e * np.sin(w * t + phi)
        pitch_deg = self.pitch_mean_deg + pitch_dev_deg

        return {
            "t": t,
            "stroke_pos": stroke_pos,
            "stroke_vel": stroke_vel,
            "x": stroke_pos * cx,
            "y": stroke_pos * cy,
            "vx": stroke_vel * cx,
            "vy": stroke_vel * cy,
            "speed": np.abs(stroke_vel),
            "pitch_deg": pitch_deg,
            "pitch_dev_deg": pitch_dev_deg,
            "alpha_rad": np.radians(pitch_deg),
        }
