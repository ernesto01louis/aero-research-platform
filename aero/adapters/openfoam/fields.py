"""Wall-field post-processing for the OpenFOAM adapter.

The TMR V&V cases compare skin-friction (Cf) and pressure (Cp) *distributions*
along a wall — not just force coefficients. The TMR case writer attaches a
`wallShearStress` field function object and a `surfaces` sampler (raw format)
to the case; this module reads that raw columnar output.

The `surfaces` function object writes, under
`postProcessing/sampleWall/<time>/`, one file per field:

    p_wall.raw                 columns: x y z p
    wallShearStress_wall.raw   columns: x y z tau_x tau_y tau_z

For the incompressible solve (kinematic pressure, unit freestream speed and
density) the coefficients are

    Cp = (p - p_inf) / (0.5 * U_inf^2) = 2 * p
    Cf = tau_wall_x / (0.5 * U_inf^2)  = `_CF_SIGN` * 2 * tau_x

`tau` from the `wallShearStress` object is the kinematic wall shear stress; its
streamwise component is negative for attached `+x` flow, so `_CF_SIGN` flips it
to the positive engineering convention.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

# Streamwise wall-shear sign: OpenFOAM's wallShearStress x-component is
# negative for attached +x flow; flip it to the positive Cf convention.
_CF_SIGN = -1.0
_U_INF = 1.0


class WallDistribution(BaseModel):
    """Cf and Cp sampled along a wall patch, ordered by streamwise coordinate."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    patch: str = Field(..., min_length=1, description="The sampled wall patch.")
    x: list[float] = Field(..., description="Streamwise coordinate, ascending.")
    cp: list[float] = Field(..., description="Pressure coefficient, paired with `x`.")
    cf: list[float] = Field(..., description="Skin-friction coefficient, paired with `x`.")

    def as_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """`(x, cp, cf)` as numpy arrays."""
        return np.asarray(self.x), np.asarray(self.cp), np.asarray(self.cf)


class FieldExtractionError(RuntimeError):
    """The sampled-surface output could not be located or parsed."""


def _latest_time_dir(sample_root: Path) -> Path:
    """The highest-numbered time directory under a `surfaces` sample tree."""
    if not sample_root.is_dir():
        raise FieldExtractionError(
            f"no sampled-surface output at {sample_root} — did the solve write postProcessing?"
        )
    times = [d for d in sample_root.iterdir() if d.is_dir()]
    numeric = [(float(d.name), d) for d in times if _is_float(d.name)]
    if not numeric:
        raise FieldExtractionError(f"no time directories under {sample_root}")
    return max(numeric, key=lambda t: t[0])[1]


def _is_float(s: str) -> bool:
    try:
        float(s)
    except ValueError:
        return False
    return True


def _read_raw(path: Path, *, n_value_cols: int) -> np.ndarray:
    """Read an OpenFOAM `raw`-format surface file: `x y z <values...>`."""
    if not path.is_file():
        raise FieldExtractionError(f"sampled-surface file not found: {path}")
    data = np.loadtxt(path, comments="#", ndmin=2)
    expected = 3 + n_value_cols
    if data.shape[1] != expected:
        raise FieldExtractionError(
            f"{path}: expected {expected} columns (x y z + {n_value_cols}), got {data.shape[1]}"
        )
    return np.asarray(data, dtype=np.float64)


def extract_wall_distributions(post_processing: Path, *, patch: str = "wall") -> WallDistribution:
    """Build the Cf / Cp wall distribution from a finished TMR solve.

    `post_processing` is the case's `postProcessing/` directory. The pressure
    and wall-shear-stress raw files for `patch` are read, the streamwise
    coordinate is sorted ascending, and the coefficients are formed.
    """
    sample_root = Path(post_processing) / "sampleWall"
    time_dir = _latest_time_dir(sample_root)

    p_raw = _read_raw(time_dir / f"p_{patch}.raw", n_value_cols=1)
    tau_raw = _read_raw(time_dir / f"wallShearStress_{patch}.raw", n_value_cols=3)

    order = np.argsort(p_raw[:, 0])
    x = p_raw[order, 0]
    cp = 2.0 / (_U_INF**2) * p_raw[order, 3]

    # The wall-shear file is sampled on the same patch; sort it the same way
    # and align on x (the two samplers visit the patch faces in the same order,
    # but sorting both on x makes the pairing explicit and order-independent).
    tau_order = np.argsort(tau_raw[:, 0])
    tau_x = tau_raw[tau_order, 0]
    if tau_x.shape != x.shape or not np.allclose(tau_x, x, rtol=0, atol=1e-9):
        raise FieldExtractionError(
            f"p and wallShearStress samples for patch {patch!r} do not share an x-grid"
        )
    cf = _CF_SIGN * 2.0 / (_U_INF**2) * tau_raw[tau_order, 3]

    return WallDistribution(
        patch=patch,
        x=[float(v) for v in x],
        cp=[float(v) for v in cp],
        cf=[float(v) for v in cf],
    )
