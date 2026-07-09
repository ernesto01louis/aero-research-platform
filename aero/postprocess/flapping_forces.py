"""Flapping-wing hover force normalisation (Wang, Birch & Dickinson 2004).

The single home for turning a dimensional OpenFOAM `forces` history into the lift/drag
coefficients the flapping literature reports, so the loader, the V&V evaluator, the GCI
script, and the reportable composer never disagree on the definition.

**Hover has no freestream**, so OpenFOAM's `forceCoeffs` (which divides by ``magUInf``) is
meaningless: the case writes only the dimensional `forces` FO, and the reference velocity is
the wing's own motion. Two coefficient conventions are produced:

* **WBD normalisation (the anchor).** WBD (2004) normalise the instantaneous force by the
  *peak quasi-steady force* over the cycle (their Eqs 14-15, a 2-D fit)::

      C_L,qs(alpha) = 1.2 sin(2 alpha)        C_D,qs(alpha) = 1.4 - cos(2 alpha)
      N_L = max_t[ 0.5 rho c u(t)^2 C_L,qs(alpha(t)) ]     (N_D analogous)
      C_L(t) = F_lift(t) / N_L                              C_D(t) = F_drag(t) / N_D

  This reproduces the paper's reported coefficients exactly (their 2-D symmetric mean C_L
  = 0.82, experiment 0.86), so the platform's numbers compare 1:1 with the published values.

* **Conventional C(U_max)** = ``F / (0.5 rho u_ref^2 c span)`` with ``u_ref = U_max = omega A0/2``
  — a diagnostic, normalisation-agnostic cross-check (the WBD coefficient is this divided by a
  pure kinematic constant).

Lift is the force perpendicular to the (horizontal) stroke line (vertical, supports weight);
drag is the force **opposing the instantaneous wing motion** (sign-corrected against the stroke
velocity — so mean drag is the positive power-related force, not the ~0 net horizontal force).

Solver-agnostic; stdlib + numpy + pydantic only.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from aero.postprocess.flapping_kinematics import FlappingKinematics

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

# Wang, Birch & Dickinson (2004) quasi-steady 2-D coefficient fits (their Eqs 14-15).
_CL_QS_PEAK = 1.2  # C_L,qs(alpha) = 1.2 sin(2 alpha)
_CD_QS_OFFSET = 1.4  # C_D,qs(alpha) = 1.4 - cos(2 alpha)


def wbd_quasi_steady_normalisers(
    motion: FlappingKinematics, *, rho: float, chord: float, span: float, n: int = 4096
) -> tuple[float, float]:
    """(N_L, N_D): the peak quasi-steady lift/drag forces over one post-ramp cycle (WBD).

    Evaluated on the analytic limit cycle (one period after the ramp), so the normaliser is a
    fixed property of the kinematics — independent of the CFD sampling. FAIL-LOUD if a peak is
    non-positive (a degenerate kinematics with no motion).
    """
    # One period sampled after the ramp completes (the steady limit cycle).
    t0 = (motion.ramp_cycles + 1.0) * motion.period
    t = np.linspace(t0, t0 + motion.period, n)
    kin = motion.evaluate(t)
    u = kin["speed"]
    alpha = kin["alpha_rad"]
    q = 0.5 * rho * chord * span * u**2
    cl_qs = _CL_QS_PEAK * np.sin(2.0 * alpha)
    cd_qs = _CD_QS_OFFSET - np.cos(2.0 * alpha)
    n_l = float(np.max(np.abs(q * cl_qs)))
    n_d = float(np.max(np.abs(q * cd_qs)))
    if n_l <= 0.0 or n_d <= 0.0:
        raise ValueError(
            f"degenerate WBD normalisers (N_L={n_l}, N_D={n_d}) — the flapping kinematics "
            "produced no wing motion (check stroke_amplitude / frequency)."
        )
    return n_l, n_d


class FlappingTrace(BaseModel):
    """Time-resolved flapping lift/drag coefficient traces + their stroke-averaged means."""

    model_config = _STRICT

    t: tuple[float, ...] = Field(..., description="Sample times (strictly ascending).")
    cl: tuple[float, ...] = Field(..., description="WBD-normalised lift coefficient C_L(t).")
    cd: tuple[float, ...] = Field(..., description="WBD-normalised drag coefficient C_D(t).")
    lift_force: tuple[float, ...] = Field(..., description="Dimensional lift (vertical) force.")
    drag_force: tuple[float, ...] = Field(..., description="Dimensional drag (opposing motion).")
    n_l: float = Field(..., gt=0.0, description="WBD lift normaliser (peak quasi-steady lift).")
    n_d: float = Field(..., gt=0.0, description="WBD drag normaliser (peak quasi-steady drag).")
    u_ref: float = Field(..., gt=0.0, description="U_max = omega * stroke_amplitude (diagnostic).")

    @model_validator(mode="after")
    def _lengths(self) -> FlappingTrace:
        if not (len(self.t) == len(self.cl) == len(self.cd) == len(self.lift_force)):
            raise ValueError("FlappingTrace: t/cl/cd/lift_force lengths differ")
        return self


def flapping_trace(
    t: np.ndarray,
    f_pressure: np.ndarray,
    f_viscous: np.ndarray,
    *,
    motion: FlappingKinematics,
    rho: float,
    chord: float,
    span: float,
) -> FlappingTrace:
    """Normalise a dimensional `forces` history into WBD lift/drag coefficient traces.

    ``f_pressure`` / ``f_viscous`` are ``(N, 2)`` in-plane (x, y) force components from the
    OpenFOAM `forces` FO (as returned by the adapter's ``_read_force_history``). Lift = total
    vertical force ``F_y``; drag = total in-line force projected onto the wing's direction of
    motion and negated (the force opposing motion). Both are divided by the fixed WBD
    quasi-steady normalisers.
    """
    t = np.asarray(t, dtype=np.float64)
    fx = (
        np.asarray(f_pressure, dtype=np.float64)[:, 0]
        + np.asarray(f_viscous, dtype=np.float64)[:, 0]
    )
    fy = (
        np.asarray(f_pressure, dtype=np.float64)[:, 1]
        + np.asarray(f_viscous, dtype=np.float64)[:, 1]
    )

    kin = motion.evaluate(t)
    # Stroke (motion) direction; drag opposes it. In-line force along the stroke line:
    sp = math.radians(motion.stroke_plane_deg)
    stroke_dir = np.array([math.cos(sp), math.sin(sp)])
    f_inline = fx * stroke_dir[0] + fy * stroke_dir[1]
    vel_sign = np.sign(kin["stroke_vel"])
    # Force opposing motion (drag > 0 resists): -(F . v_hat). Where the wing is momentarily
    # at rest (reversal) the sign is 0 and the instantaneous drag contribution is ~0 anyway.
    drag_force = -f_inline * vel_sign
    lift_force = fy  # vertical, perpendicular to the horizontal stroke

    n_l, n_d = wbd_quasi_steady_normalisers(motion, rho=rho, chord=chord, span=span)
    cl = lift_force / n_l
    cd = drag_force / n_d
    return FlappingTrace(
        t=tuple(float(v) for v in t),
        cl=tuple(float(v) for v in cl),
        cd=tuple(float(v) for v in cd),
        lift_force=tuple(float(v) for v in lift_force),
        drag_force=tuple(float(v) for v in drag_force),
        n_l=n_l,
        n_d=n_d,
        u_ref=motion.u_ref,
    )
