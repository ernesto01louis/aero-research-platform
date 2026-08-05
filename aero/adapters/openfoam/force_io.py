"""Read OpenFOAM ``forces`` / ``forceCoeffs`` function-object output.

Promoted out of :mod:`aero.adapters.openfoam.solver` at Stage 20, where a second consumer
appears: the coupled FSI readout reads the fluid participant's force history directly,
without going through ``OpenFOAMSolver.load()`` (the coupled path has its own ``load``).
The functions are unchanged apart from :func:`read_force_history` now REPORTING what it
dropped -- see below.

**Why the drop count matters.** OpenFOAM writes force rows at ``timePrecision`` digits
(default 6). Two rows whose true times differ by less than that collapse to the same
printed string, and :func:`strictly_increasing_mask` -- which exists because a ``Signal``
needs strictly-ascending time -- then deletes one of them. At the Stage-11/13 write
intervals that never happened. At Stage 20's coupling time-window size it happens
routinely unless the deck sets ``timePrecision 12``, and it happens SILENTLY: the series
is shorter than the run, the cycle segmentation still succeeds, and the reported cycle
means are computed from a record with holes in it. So the reader now returns
``n_dropped`` and the readout raises when it is non-zero, rather than each caller
rediscovering the trap.

stdlib + numpy only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "ForceHistory",
    "read_coefficient_dat",
    "read_force_history",
    "strictly_increasing_mask",
]


@dataclass(frozen=True, slots=True)
class ForceHistory:
    """A force time series and the number of rows the de-duplication removed.

    An object rather than a 4-tuple on purpose: a tuple's fourth element is exactly what a
    caller written by analogy with the old three-element unpacking would drop, and
    ``n_dropped`` silently dropped is the failure this promotion exists to prevent.
    """

    t: NDArray[np.float64]
    pressure: NDArray[np.float64]
    viscous: NDArray[np.float64]
    n_dropped: int


def strictly_increasing_mask(t: NDArray[np.float64]) -> NDArray[np.bool_]:
    """Boolean mask keeping only rows whose time strictly exceeds all earlier times.

    OpenFOAM force/forceCoeffs FO output can carry **duplicate timestamps**: with
    ``adjustTimeStep`` + ``adjustableRunTime`` writes the solver takes a sub-step to land
    exactly on a write time, and the FO records both at the same (written-precision) time
    (a restart can also re-append). A ``Signal`` needs strictly-ascending time, so dedupe
    by keeping the first row at each new maximum time. (Frequent writes -- e.g. the foil's
    0.02 interval -- trigger this; the cylinder's 0.1 interval did not.)
    """
    if len(t) == 0:
        return np.zeros(0, dtype=bool)
    run_max = np.maximum.accumulate(t)
    keep = np.empty(len(t), dtype=bool)
    keep[0] = True
    keep[1:] = t[1:] > run_max[:-1]
    return keep


def read_force_history(path: Path) -> ForceHistory:
    """``(times, pressure_xy, viscous_xy)`` from a ``forces`` FO ``force.dat``, plus drops.

    Handles both layouts (parenthesised vector form and the flat ESI columns) the
    Stage-10 ``_read_force_decomposition`` parses, but for every row (a time series, not
    just the last row) -- the moving cases need the full history for cycle-mean forces and
    the plunging-foil thrust/power integrals. Arrays are ``t`` (N,), ``pressure`` (N,2),
    ``viscous`` (N,2) -- the in-plane (x, y) components.
    """
    times: list[float] = []
    pressures: list[list[float]] = []
    viscous: list[list[float]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "(" in s:
            t = float(s.split("(", 1)[0].split()[0])
            triples = re.findall(r"\(([^()]*)\)", s)
            if len(triples) < 2:
                raise ValueError(f"unexpected parenthesised forces layout in {path}: {s!r}")
            fp = [float(v) for v in triples[0].split()]
            fv = [float(v) for v in triples[1].split()]
        else:
            nums = [float(v) for v in s.split()]
            if len(nums) < 10:
                raise ValueError(f"unexpected flat forces layout in {path}: {s!r}")
            t, fp, fv = nums[0], nums[4:7], nums[7:10]
        times.append(t)
        pressures.append(fp[:2])
        viscous.append(fv[:2])
    if not times:
        raise ValueError(f"no data rows in forces file {path}")
    t_arr = np.asarray(times, dtype=np.float64)
    fp_arr = np.asarray(pressures, dtype=np.float64)
    fv_arr = np.asarray(viscous, dtype=np.float64)
    keep = strictly_increasing_mask(t_arr)  # dedupe duplicate FO timestamps
    return ForceHistory(
        t_arr[keep], fp_arr[keep], fv_arr[keep], int(t_arr.size - int(np.count_nonzero(keep)))
    )


def read_coefficient_dat(path: Path) -> tuple[list[str], NDArray[np.float64]]:
    """Return (column names, data array) from an OpenFOAM coefficient file."""
    header: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            header = stripped.lstrip("#").split()  # last comment line wins
        elif stripped:
            break
    data = np.loadtxt(path, comments="#", ndmin=2)
    if "Cd" not in header or "Cl" not in header:
        raise ValueError(f"unexpected coefficient-file columns {header} in {path}")
    return header, np.asarray(data, dtype=np.float64)
