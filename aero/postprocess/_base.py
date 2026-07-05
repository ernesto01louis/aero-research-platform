"""Core types for the unsteady post-processing toolkit (Stage 11).

PLATFORM-NOT-HUB: stdlib + numpy + pydantic only. Strict pydantic (``extra='forbid'``,
frozen). These types are **solver-agnostic** — a :class:`Signal` is any scalar time
series (a lift coefficient, a thrust force, a moment, ...); the toolkit turns such
signals into the derived unsteady quantities the flapping optimizer's objective is
built from (Strouhal/frequency, phase-averaged loads, thrust / power / propulsive
efficiency, viscous/pressure force split, and the periodic-steady-state check).

The :class:`Signal` is the unit the toolkit consumes and the unit Stage 12's
statistical-U95 (batch-means / N_eff) machinery is built on top of (via the
per-cycle samples in :mod:`aero.postprocess.phase_averaging`).
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Shared strict config — mirrors aero/adapters/openfoam/cylinder.py:_STRICT and the
# fail-loud-pydantic rule: unknown keys raise, models are immutable after construction.
_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class Signal(BaseModel):
    """A scalar time series ``y(t)`` — the unit the toolkit consumes.

    ``t`` must be strictly ascending and the same length as ``y`` (>= 4, enough to
    resolve a cycle and an FFT peak with parabolic interpolation). Samples need not
    be exactly uniform — OpenFOAM's ``adjustableRunTime`` force writes are only
    near-uniform — so the frequency estimator uses the mean spacing and the
    cycle-segmentation bins by time.
    """

    model_config = _STRICT

    t: tuple[float, ...] = Field(..., min_length=4, description="Ascending sample times.")
    y: tuple[float, ...] = Field(..., min_length=4, description="Signal values at ``t``.")
    name: str = Field(..., min_length=1, description="Signal name, e.g. 'lift_coefficient'.")

    @model_validator(mode="after")
    def _consistent(self) -> Signal:
        if len(self.t) != len(self.y):
            raise ValueError(f"Signal {self.name!r}: len(t)={len(self.t)} != len(y)={len(self.y)}")
        if not bool(np.all(np.diff(self.t_array) > 0.0)):
            raise ValueError(f"Signal {self.name!r}: t must be strictly ascending")
        return self

    @classmethod
    def from_arrays(
        cls, t: np.ndarray | list[float], y: np.ndarray | list[float], *, name: str
    ) -> Signal:
        """Build a ``Signal`` from numpy arrays / lists (the adapter's entry point)."""
        return cls(
            t=tuple(float(v) for v in t),
            y=tuple(float(v) for v in y),
            name=name,
        )

    @property
    def t_array(self) -> np.ndarray:
        return np.asarray(self.t, dtype=np.float64)

    @property
    def y_array(self) -> np.ndarray:
        return np.asarray(self.y, dtype=np.float64)

    @property
    def duration(self) -> float:
        """Total time span ``t[-1] - t[0]``."""
        return self.t[-1] - self.t[0]
