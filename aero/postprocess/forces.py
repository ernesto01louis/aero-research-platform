"""Viscous / pressure force decomposition as a first-class, closure-checked type.

Generalises the Stage-10 ``forces``-function-object drag split (which lived inline in
the OpenFOAM adapter) into a typed :class:`ForceDecomposition` whose validator
**enforces closure** — pressure + viscous must reconstruct the independently-computed
total, or construction fails loud. This is the GO-gate "force decomposition closes to
total within tolerance" as a schema invariant rather than a hand-rolled ``if``.

Solver-agnostic: the OpenFOAM-specific parsing of the ``force.dat`` layout stays in the
adapter; this module takes already-parsed force vectors (or coefficients) and produces
the typed, validated output any case can carry.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field, model_validator

from aero.postprocess._base import _STRICT


class ForceDecomposition(BaseModel):
    """A force (or force-coefficient) split into pressure and viscous parts.

    The validator requires ``pressure + viscous`` to reconstruct ``total`` within
    ``closure_tol_abs + closure_tol_rel * |total|`` (default 1e-3 + 1% — the same band
    the Stage-10 adapter used). A gross mismatch means a mis-parsed force layout or an
    inconsistent total, and must not pass silently (FAIL-LOUD).
    """

    model_config = _STRICT

    total: float = Field(..., description="Independently-computed total (e.g. forceCoeffs Cd).")
    pressure: float = Field(..., description="Pressure (form) component.")
    viscous: float = Field(..., description="Viscous (friction) component.")
    closure_tol_abs: float = Field(default=1.0e-3, gt=0.0)
    closure_tol_rel: float = Field(default=1.0e-2, gt=0.0)

    @model_validator(mode="after")
    def _closes(self) -> ForceDecomposition:
        recon = self.pressure + self.viscous
        if abs(recon - self.total) > self.closure_tol_abs + self.closure_tol_rel * abs(self.total):
            raise ValueError(
                f"force decomposition does not close: pressure+viscous={recon:.6g} "
                f"disagrees with total={self.total:.6g}"
            )
        return self


def _project(force_xy: Sequence[float], direction: tuple[float, float], q_aref: float) -> float:
    """Project a 2-D force onto ``direction`` and normalise by dynamic pressure x area."""
    if q_aref <= 0.0:
        raise ValueError(f"q_aref must be positive, got {q_aref}")
    return (force_xy[0] * direction[0] + force_xy[1] * direction[1]) / q_aref


def decompose_drag(
    *,
    pressure_force: Sequence[float],
    viscous_force: Sequence[float],
    direction: tuple[float, float],
    q_aref: float,
    total: float,
) -> ForceDecomposition:
    """Build a closure-checked :class:`ForceDecomposition` from pressure/viscous vectors.

    Projects the two force vectors onto the drag ``direction`` (``(cos aoa, sin aoa)``),
    normalises by ``q_aref = 0.5 * rho * U^2 * Aref``, and checks the split against the
    independently-computed ``total`` coefficient. Raises (via the validator) if the split
    does not close — the caller's parser mis-read the layout.
    """
    cd_pressure = _project(pressure_force, direction, q_aref)
    cd_viscous = _project(viscous_force, direction, q_aref)
    return ForceDecomposition(total=total, pressure=cd_pressure, viscous=cd_viscous)
