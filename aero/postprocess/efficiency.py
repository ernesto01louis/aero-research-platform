"""Thrust, input power, and propulsive efficiency for a plunging (heaving) body.

The flapping optimizer's objective is built from these: a plunging foil produces a
time-mean thrust while the actuator does work against the fluid to oscillate it; the
propulsive efficiency ``eta = thrust power / input power`` is the quantity to optimize
at fixed thrust. Definitions (pure heave ``y(t) = h0 sin(omega t)``, matching OpenFOAM's
``oscillatingDisplacement``; velocity ``ydot(t) = h0 omega cos(omega t)``):

* thrust ``T = -<F_x>`` (streamwise aerodynamic force is drag-positive, so net thrust is
  a negative mean F_x); ``C_T = T / (0.5 rho U^2 A)``.
* input power ``P_in = <-F_y * ydot>`` — the actuator work against the transverse
  aerodynamic force (positive for a thrust-producing foil); ``C_P = P_in / (0.5 rho U^3 A)``.
* propulsive efficiency ``eta = T*U / P_in = C_T / C_P`` — defined only when the foil is a
  net propulsor doing net positive work (``C_T > 0`` and ``C_P > 0``); ``None`` otherwise
  (below the net-thrust threshold, or energy-extracting), so a St-sweep can still report
  ``C_T`` through the sign change.

Averages are taken over an **integer number of cycles** (trapezoidal) so the mean is not
biased by a partial period. Solver-agnostic; stdlib + numpy + pydantic only.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel, Field

from aero.postprocess._base import _STRICT, Signal
from aero.postprocess.phase_averaging import _cycle_bounds


class MotionKinematics(BaseModel):
    """Prescribed pure-heave kinematics ``y(t) = amplitude * sin(omega * t)``."""

    model_config = _STRICT

    amplitude: float = Field(..., gt=0.0, description="Heave amplitude h0 (length units).")
    omega: float = Field(..., gt=0.0, description="Angular frequency (rad/time).")

    @property
    def period(self) -> float:
        return 2.0 * math.pi / self.omega

    def displacement(self, t: np.ndarray) -> np.ndarray:
        return self.amplitude * np.sin(self.omega * t)

    def velocity(self, t: np.ndarray) -> np.ndarray:
        return self.amplitude * self.omega * np.cos(self.omega * t)


class PropulsiveMetrics(BaseModel):
    """Time-mean thrust / power coefficients and propulsive efficiency."""

    model_config = _STRICT

    thrust_coefficient: float = Field(..., description="C_T = -<F_x> / (0.5 rho U^2 A).")
    power_coefficient: float = Field(..., description="C_P = <-F_y*ydot> / (0.5 rho U^3 A).")
    propulsive_efficiency: float | None = Field(
        default=None, description="eta = C_T / C_P; None unless C_T>0 and C_P>0."
    )
    strouhal: float = Field(
        ..., ge=0.0, description="St = 2 f h0 / U (Heathcote-Gursul convention)."
    )
    n_cycles: int = Field(..., ge=1, description="Full cycles averaged over.")


def propulsive_metrics(
    *,
    fx: Signal,
    fy: Signal,
    kin: MotionKinematics,
    rho: float,
    u_inf: float,
    ref_area: float,
    drop_initial_cycles: int = 0,
) -> PropulsiveMetrics:
    """Thrust / power / efficiency from streamwise & transverse force histories.

    ``fx`` / ``fy`` are the dimensional aerodynamic force time series (same time base);
    ``ref_area`` is the reference area (chord x span). Averages run over the integer
    number of cycles available after ``drop_initial_cycles`` — pass the converged tail.
    """
    if rho <= 0.0 or u_inf <= 0.0 or ref_area <= 0.0:
        raise ValueError(f"need positive rho ({rho}), u_inf ({u_inf}), ref_area ({ref_area})")
    t = fx.t_array
    if not np.allclose(t, fy.t_array):
        raise ValueError("propulsive_metrics: fx and fy must share the same time base")

    period = kin.period
    t0, n_full = _cycle_bounds(fx, period=period, drop_initial_cycles=drop_initial_cycles)
    t_end = t0 + n_full * period
    mask = (t >= t0 - 1.0e-12) & (t <= t_end + 1.0e-12)
    tw = t[mask]
    fxw = fx.y_array[mask]
    fyw = fy.y_array[mask]
    if tw.size < 4:
        raise ValueError("propulsive_metrics: too few samples in the integer-cycle window")

    span = float(tw[-1] - tw[0])
    ydot = kin.velocity(tw)
    thrust_mean = -float(np.trapezoid(fxw, tw)) / span  # -<F_x>
    p_in = float(np.trapezoid(-fyw * ydot, tw)) / span  # <-F_y * ydot>

    q = 0.5 * rho * u_inf**2
    c_t = thrust_mean / (q * ref_area)
    c_p = p_in / (q * ref_area * u_inf)
    eta = (c_t / c_p) if (c_t > 0.0 and c_p > 0.0) else None
    strouhal = kin.omega * kin.amplitude / (math.pi * u_inf)  # 2 f h0 / U

    return PropulsiveMetrics(
        thrust_coefficient=c_t,
        power_coefficient=c_p,
        propulsive_efficiency=eta,
        strouhal=strouhal,
        n_cycles=n_full,
    )
