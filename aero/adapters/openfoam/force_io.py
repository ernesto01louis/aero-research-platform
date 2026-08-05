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

**A second, different reason a time repeats: implicit coupling.** Under
``parallel-implicit`` preCICE re-does a time window until it converges, the OpenFOAM
adapter rewinds ``runTime``, and the ``forces`` object re-executes and re-appends. So a
coupled ``force.dat`` carries one row PER COUPLING ITERATION at each window time, and only
the LAST of them is the converged iterate. That is exactly how
:mod:`aero.adapters.precice.ccx_dat` treats the CalculiX ``.dat``, and how
``flexible_foil``'s own interface-power object documents its cadence -- but
:func:`strictly_increasing_mask` keeps the **first**. Left alone, the coupled readout
would build ``C_T`` from unconverged iterates while ``P2`` and ``P3`` came from converged
ones, ``eta`` would mix the two, and -- because the flexible arm needs more coupling
iterations than the rigid one -- the resulting bias would DIFFER BETWEEN ARMS and land
directly in the gated increment. Nothing downstream could see it: after de-duplication
both arms carry one row per window at identical times, so the cross-arm alignment check
passes, and D10 compares two quantities that are both taken from the last iterate.

The fix is a policy argument rather than a change of behaviour. ``repeats="first"`` is the
default and is byte-for-byte what Stage 10/11/13 have always done, so no existing record
moves; the coupled readout passes ``repeats="last"`` and, separately, proves with
:func:`classify_repeat_cadence` that the repeat count is exactly what the coupling's own
iteration log accounts for. Anything else raises -- an unexplained repeat is a
``timePrecision`` collapse, which is the failure ``n_dropped`` exists to report.

stdlib + numpy only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "ForceHistory",
    "RepeatCadence",
    "Repeats",
    "classify_repeat_cadence",
    "last_occurrence_mask",
    "read_coefficient_dat",
    "read_force_history",
    "strictly_increasing_mask",
]

#: How to resolve rows that share a printed time.
#:
#: * ``"first"`` -- keep the first (Stage 10/11/13 behaviour; the default, unchanged);
#: * ``"last"`` -- keep the last, which under implicit coupling is the CONVERGED iterate;
#: * ``"raw"`` -- keep everything, so a caller can classify the repeats before choosing.
Repeats = Literal["first", "last", "raw"]


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


def last_occurrence_mask(t: NDArray[np.float64]) -> NDArray[np.bool_]:
    """Boolean mask keeping the LAST row at each distinct time.

    The counterpart to :func:`strictly_increasing_mask`, for the implicit-coupling case
    where a repeated time is a re-done coupling iteration rather than a write-precision
    collision. Under ``parallel-implicit`` only the last iterate at a window time is the
    converged one, so keeping the first would report the solver's first guess.

    Equality is exact, which is correct here: every row at one window carries the same
    printed time and therefore the same float. Deliberately identical in behaviour to
    ``ccx_dat._last_occurrence`` -- the two files describe the same phenomenon, and having
    them disagree is what this function exists to stop.
    """
    if len(t) == 0:
        return np.zeros(0, dtype=bool)
    last: dict[float, int] = {}
    for index, value in enumerate(t):
        last[float(value)] = index
    keep = np.zeros(len(t), dtype=bool)
    keep[np.asarray(sorted(last.values()), dtype=np.int64)] = True
    return keep


@dataclass(frozen=True, slots=True)
class RepeatCadence:
    """Why a force record's times repeat, established structurally rather than assumed."""

    kind: Literal["per-window", "per-iteration"]
    n_rows: int
    n_distinct: int
    n_repeats: int


def classify_repeat_cadence(
    t: NDArray[np.float64], *, n_windows: int, total_iterations: int
) -> RepeatCadence:
    """Classify a coupled record's repeated times against the coupling's own iteration log.

    Structural, never assumed -- the same three-way test
    :func:`aero.adapters.precice.ccx_dat.read_reaction_forces` applies to the CalculiX
    ``.dat``:

    * no repeats at all means the object wrote once per completed window;
    * exactly ``total_iterations - n_windows`` repeats means it wrote once per coupling
      ITERATION, which is what an implicit scheme produces;
    * anything else is unexplained, and the likeliest cause is a ``timePrecision`` too
      coarse for the time-window size -- consecutive rows collapsing to one printed time.
      That is silent data loss, so it raises rather than picking whichever branch is
      closer.

    ``total_iterations`` is the sum over windows of the iterations the participant's own
    ``precice-<Participant>-iterations.log`` recorded, so the two records have to agree
    about how many times the window was solved.
    """
    n_rows = int(np.asarray(t).size)
    n_distinct = int(np.unique(np.asarray(t, dtype=np.float64)).size)
    n_repeats = n_rows - n_distinct
    if n_repeats == 0:
        return RepeatCadence("per-window", n_rows, n_distinct, n_repeats)
    expected = total_iterations - n_windows
    if n_repeats == expected:
        return RepeatCadence("per-iteration", n_rows, n_distinct, n_repeats)
    raise ValueError(
        f"{n_rows} rows carry {n_distinct} distinct times ({n_repeats} repeats), which the "
        f"coupling does not account for: {n_windows} windows took {total_iterations} "
        f"iterations, so an implicit record would repeat exactly {expected} times and a "
        "per-window record not at all. The usual cause is a timePrecision too coarse for "
        "the time-window size, which deletes rows silently; the deck sets timePrecision 12 "
        "for exactly that reason."
    )


def read_force_history(path: Path, *, repeats: Repeats = "first") -> ForceHistory:
    """``(times, pressure_xy, viscous_xy)`` from a ``forces`` FO ``force.dat``, plus drops.

    Handles both layouts (parenthesised vector form and the flat ESI columns) the
    Stage-10 ``_read_force_decomposition`` parses, but for every row (a time series, not
    just the last row) -- the moving cases need the full history for cycle-mean forces and
    the plunging-foil thrust/power integrals. Arrays are ``t`` (N,), ``pressure`` (N,2),
    ``viscous`` (N,2) -- the in-plane (x, y) components.

    ``repeats`` chooses which row survives a shared printed time; see :data:`Repeats` and
    the module docstring. The default is the Stage-10/11/13 behaviour and is not to be
    changed: those records were read with it.
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
    match repeats:
        case "first":
            keep = strictly_increasing_mask(t_arr)
        case "last":
            keep = last_occurrence_mask(t_arr)
        case "raw":
            keep = np.ones(t_arr.size, dtype=bool)
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
