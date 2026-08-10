"""Read pimpleFoam's per-step Courant lines out of a participant log — gate I7's input.

pimpleFoam prints ``Courant Number mean: <m> max: <M>`` once per time step regardless of
``adjustTimeStep``. Under IMPLICIT coupling the preCICE adapter rewinds ``runTime`` and
the solver re-prints the step, so both ``Time =`` and Courant lines repeat per coupling
iteration; every Courant line here is therefore paired with the MOST RECENT ``Time =``
line above it, and a maximum over any window is repeat-insensitive (the re-done step
prints the same converged-state Courant or a smaller provisional one — never a larger
one that the physics did not produce; I7 gates the maximum, so extra repeats can only
be conservative).

Stdlib + numpy + pydantic only (Invariant 1). The precedent for reading a participant
log is ``flexible_foil.read_interface_power``.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

__all__ = ["CourantHistory", "SolverLogError", "read_courant_history"]

_TIME_LINE = re.compile(r"^Time = (?P<time>[0-9eE+.\-]+)\s*$", re.MULTILINE)
_COURANT_LINE = re.compile(
    r"^Courant Number mean: (?P<mean>[0-9eE+.\-]+) max: (?P<max>[0-9eE+.\-]+)\s*$",
    re.MULTILINE,
)


class SolverLogError(Exception):
    """The log does not carry what the probe needs; the reason is the message."""


class CourantHistory(BaseModel):
    """Every Courant line, paired with the ``Time =`` it was printed under."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    t: tuple[float, ...] = Field(..., min_length=1)
    mean: tuple[float, ...] = Field(..., min_length=1)
    max: tuple[float, ...] = Field(..., min_length=1)
    n_lines: int = Field(..., ge=1, description="Courant lines read, repeats included.")

    def max_over(self, *, t_start: float) -> float:
        """The maximum Courant number at or after ``t_start`` — I7's measured quantity."""
        t = np.asarray(self.t, dtype=np.float64)
        window: NDArray[np.bool_] = t >= t_start
        if not bool(window.any()):
            raise SolverLogError(
                f"no Courant line at or after t = {t_start!r}: the log ends at "
                f"t = {max(self.t)!r}, so the probe never reached the window it was "
                "meant to measure — the maximum would describe the ramp, not the "
                "post-ramp regime"
            )
        return float(np.asarray(self.max, dtype=np.float64)[window].max())


def read_courant_history(log_path: Path) -> CourantHistory:
    """Parse the fluid participant's log; every Courant line keeps its printed time."""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SolverLogError(f"cannot read {log_path}: {exc}") from exc

    events: list[tuple[float, float, float]] = []
    current_time: float | None = None
    matches = sorted(
        [(m.start(), "time", m) for m in _TIME_LINE.finditer(text)]
        + [(m.start(), "courant", m) for m in _COURANT_LINE.finditer(text)],
        key=lambda item: item[0],
    )
    for _, kind, match in matches:
        if kind == "time":
            current_time = float(match.group("time"))
        else:
            if current_time is None:
                # OpenFOAM prints the very first Courant line BEFORE the first
                # "Time =" (the t=0 state during initialisation); attribute it to 0.
                current_time = 0.0
            events.append((current_time, float(match.group("mean")), float(match.group("max"))))

    if not events:
        raise SolverLogError(
            f"{log_path} carries no 'Courant Number mean: ... max: ...' lines — either "
            "the solve never took a step or this is not a pimpleFoam participant log"
        )
    return CourantHistory(
        t=tuple(e[0] for e in events),
        mean=tuple(e[1] for e in events),
        max=tuple(e[2] for e in events),
        n_lines=len(events),
    )
