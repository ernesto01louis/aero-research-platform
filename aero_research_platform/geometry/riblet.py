"""Blade-riblet profile generator (Bechert 1997 reference geometry).

Reference: Bechert, Bruse, Hage, van der Hoeven, Hoppe (1997), "Experiments on
drag-reducing surfaces and their optimization with an adjustable geometry",
J. Fluid Mech. 338:59-87 (DOI 10.1017/S0022112096004673).

A *blade* riblet is a thin vertical fin of height ``h`` and spanwise thickness
``t`` repeated at pitch ``s`` along the wall-parallel direction transverse to
the streamwise axis. The standard Bechert blade-riblet geometry uses
``h/s = 0.5`` and ``t/s = 0.02`` (sharp tip). Drag-reduction performance is
plotted against the wall-unit pitch

    s+ = s * u_tau / nu

with peak DR ~9.9% near s+ ≈ 17 and crossover s+ ≈ 27 for the blade variant
(Heidarian et al. JAFM 11(3):679-688, 2018 — Table comparing literature
values, "Oil Blade Riblet" column citing Bechert).

The generator below emits a single closed CCW profile in the spanwise (y) /
wall-normal (z) plane spanning ``n_pitches`` consecutive periods. Suitable
for extrusion along the streamwise (x) axis to build a periodic-strip STL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

# Bechert blade-riblet canonical aspect ratios (Fig 5 of the 1997 paper).
BECHERT_BLADE_H_OVER_S: Final[float] = 0.5
BECHERT_BLADE_T_OVER_S: Final[float] = 0.02


@dataclass(frozen=True)
class BladeRibletSpec:
    """One blade-riblet period geometry.

    Args:
        pitch_s: spanwise distance between adjacent blade centrelines.
        h_over_s: blade height as a fraction of pitch (Bechert: 0.5).
        t_over_s: blade thickness as a fraction of pitch (Bechert: 0.02).
    """

    pitch_s: float
    h_over_s: float = BECHERT_BLADE_H_OVER_S
    t_over_s: float = BECHERT_BLADE_T_OVER_S

    def __post_init__(self) -> None:
        if self.pitch_s <= 0.0:
            raise ValueError("pitch_s must be positive")
        if self.h_over_s <= 0.0:
            raise ValueError("h_over_s must be positive")
        if not 0.0 < self.t_over_s < 1.0:
            raise ValueError("t_over_s must lie in (0, 1)")

    @property
    def height_h(self) -> float:
        return self.h_over_s * self.pitch_s

    @property
    def thickness_t(self) -> float:
        return self.t_over_s * self.pitch_s


def s_from_s_plus(s_plus: float, u_tau: float, nu: float) -> float:
    """Physical pitch ``s`` corresponding to a target wall-unit pitch ``s+``.

    s+ = s * u_tau / nu, so s = s_plus * nu / u_tau.

    Args:
        s_plus: target wall-unit pitch (dimensionless).
        u_tau: friction velocity at the measurement station (m/s; consistent
            units with ``nu``).
        nu: kinematic viscosity (m^2/s).
    """
    if s_plus <= 0.0:
        raise ValueError("s_plus must be positive")
    if u_tau <= 0.0:
        raise ValueError("u_tau must be positive")
    if nu <= 0.0:
        raise ValueError("nu must be positive")
    return s_plus * nu / u_tau


def s_plus_from_s(s: float, u_tau: float, nu: float) -> float:
    """Inverse of :func:`s_from_s_plus` — wall-unit pitch from physical pitch."""
    if s <= 0.0:
        raise ValueError("s must be positive")
    if u_tau <= 0.0:
        raise ValueError("u_tau must be positive")
    if nu <= 0.0:
        raise ValueError("nu must be positive")
    return s * u_tau / nu


def blade_period_profile(spec: BladeRibletSpec) -> tuple[np.ndarray, np.ndarray]:
    """Single-period blade-riblet profile in the (y, z) plane.

    Origin at the left edge of one period, z = 0 on the wall. The profile
    is traversed CCW: left valley → blade-left flank up → blade tip → blade-right
    flank down → right valley. Six points, closed by the caller via
    :func:`blade_strip_profile` when stitched over multiple periods.

    Returns ``(y, z)`` numpy float64 arrays, length 6.
    """
    s = spec.pitch_s
    h = spec.height_h
    t = spec.thickness_t
    y_left_flank = 0.5 * (s - t)
    y_right_flank = 0.5 * (s + t)
    y = np.array([0.0, y_left_flank, y_left_flank, y_right_flank, y_right_flank, s], dtype=np.float64)
    z = np.array([0.0, 0.0, h, h, 0.0, 0.0], dtype=np.float64)
    return y, z


def blade_strip_profile(
    spec: BladeRibletSpec,
    n_pitches: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Profile spanning ``n_pitches`` consecutive blades, CCW.

    Adjacent periods share their valley point so the returned point count is
    ``5 * n_pitches + 1`` rather than ``6 * n_pitches``.
    """
    if n_pitches < 1:
        raise ValueError("n_pitches must be >= 1")
    y_one, z_one = blade_period_profile(spec)
    ys = [y_one]
    zs = [z_one]
    for k in range(1, n_pitches):
        ys.append(y_one[1:] + k * spec.pitch_s)
        zs.append(z_one[1:])
    return np.concatenate(ys), np.concatenate(zs)
