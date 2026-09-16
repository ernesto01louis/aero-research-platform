"""Coupling-window indices: the one place a participant's time STAMP is interpreted.

Under implicit coupling the two participants of the Stage-20 case stamp their per-window
output at **different instants of the same window**, and nothing in the repo said so until
it was measured. The fluid's function objects stamp the window START; CalculiX stamps the
window END. Both records are complete and correct; they simply do not mean what a shared
float time axis says they mean.

MEASURED, on both surviving I4 arms, from bytes already on disk:

* ``force.dat`` carries ``sum(iterations)`` rows over ``n_windows + 1`` distinct times;
* the row count at distinct time ``k * dt`` EQUALS the coupling's own iteration count for
  window ``k + 1``, for every ``k >= 1`` (499/500 exact on both arms), with
  ``count[0] = it[0] - 1`` and a single trailing row at ``max_time``;
* grouping the rows that way yields a monotonically converging ``|dF|`` sequence in
  **100 %** of windows, and the alternative grouping in **0 %** — so the rows at
  ``(w-1) * dt`` are window ``w``'s fixed-point iteration, last row converged;
* the CalculiX ``.dat`` carries one row per window at ``dt .. n * dt``.

So the fluid's converged force for window ``w`` is stamped ``(w-1) * dt`` and the solid's
reaction for the SAME window is stamped ``w * dt``, and pairing the two by index-``k`` on
raw times compares different physical intervals. That lands directly in D10
(``|P3-P2|/P2``) and in P1/P3.

The fix is a WINDOW INDEX, not an offset. Every series declares the convention it was
written under, the index is derived from that declaration, and the join is on an integer.
A ``+1`` applied at one call site would be the handoff §6.22 defect wearing a fix's
clothes: correct today, invisible tomorrow, and impossible to check.

The window index is 1-based and means "the window that advanced the solution to
``index * dt``". A fluid stamp at ``t = 0`` is therefore window 1, and a fluid stamp at
``max_time`` is window ``n + 1`` — a window that does not exist, produced by the final
write after the run ends. :func:`common_windows` drops it, which is why it drops rather
than raises on a series that covers more windows than its peer.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray

# Imported rather than redefined, and imported from the OpenFOAM side deliberately:
# `force_io` has no preCICE imports, while `precice/case.py` already imports the OpenFOAM
# writers, so the reverse direction would run `precice/__init__` while `force_io` is half
# initialised. One definition, and the arrow points the only way it can.
from aero.adapters.openfoam.force_io import StampConvention

__all__ = [
    "STAMP_CONVENTIONS",
    "ScheduleError",
    "StampConvention",
    "common_windows",
    "select_windows",
    "window_indices",
]

#: The two conventions, and what each means (the type itself lives in ``force_io``).
#:
#: ``"window-start"`` -- the value carries the time the window started from. The OpenFOAM
#: function objects do this because the preCICE adapter restores the window-start
#: checkpoint (including ``runTime``) before each coupling iteration, so the FO reads a
#: reverted clock. It is not a bug in the adapter and it is not configurable.
#:
#: ``"window-end"`` -- the value carries the time the window advanced to. CalculiX's
#: ``*NODE PRINT`` does this, and it is the convention
#: ``ccx_dat.assert_matches_schedule`` already encodes (``rint(t/dt) == 1..n``).
STAMP_CONVENTIONS: tuple[StampConvention, ...] = ("window-start", "window-end")

#: How far off an exact multiple of the window a stamp may sit, as a fraction of it.
#: Generous, because these are independent ASCII accumulators written by three different
#: programs and CalculiX prints its time at seven significant digits -- but far tighter
#: than the half-window that would let a stamp land in the wrong window.
_INDEX_TOL_WINDOWS = 1.0e-3


class ScheduleError(Exception):
    """A time series cannot be placed on the coupling's window grid."""


def window_indices(
    t: NDArray[np.float64],
    *,
    time_window_size: float,
    stamp: StampConvention,
    label: str,
) -> NDArray[np.int64]:
    """The 1-based coupling window each stamp belongs to, under a DECLARED convention.

    ``label`` names the series in any error, because the whole point of this module is
    that "the times disagree" is not a usable diagnosis when three writers are involved.

    The residual of ``t / dt`` against its nearest integer is CHECKED, not assumed. A
    stamp that is not on the window grid means the reader is looking at a sub-cycled or
    adjusted-time-step record, and silently rounding it into a window would produce
    exactly the plausible-wrong-number this module exists to prevent.
    """
    if stamp not in STAMP_CONVENTIONS:
        raise ScheduleError(f"{label}: unknown stamp convention {stamp!r}")
    if time_window_size <= 0.0:
        raise ScheduleError(f"{label}: time_window_size must be positive, got {time_window_size!r}")
    times = np.asarray(t, dtype=np.float64)
    if times.size == 0:
        raise ScheduleError(f"{label}: empty time series — no window can be identified")
    scaled = times / time_window_size
    nearest = np.rint(scaled)
    worst = float(np.max(np.abs(scaled - nearest))) if times.size else 0.0
    if worst > _INDEX_TOL_WINDOWS:
        offender = int(np.argmax(np.abs(scaled - nearest)))
        raise ScheduleError(
            f"{label}: stamp {times[offender]!r} sits {worst:.3e} windows off the coupling "
            f"grid of {time_window_size!r} s, more than {_INDEX_TOL_WINDOWS:.0e}. Every "
            "per-window record lands on a multiple of the window; a record that does not "
            "is not a per-window record, and rounding it into a window would invent a "
            "pairing rather than read one"
        )
    index = nearest.astype(np.int64)
    if stamp == "window-start":
        index = index + 1
    if int(index.min()) < 1:
        raise ScheduleError(
            f"{label}: stamp {times[int(np.argmin(index))]!r} maps to window "
            f"{int(index.min())} under {stamp!r}; window indices are 1-based"
        )
    return index


def common_windows(indexed: Mapping[str, NDArray[np.int64]]) -> NDArray[np.int64]:
    """The ascending windows EVERY series covers, or a loud failure naming the gap.

    Drops rather than raises on extra windows, because one extra is expected: the fluid
    writes once more after the last window closes, at ``max_time``, which maps to window
    ``n + 1``. Raising on that would refuse every real run. A series MISSING windows its
    peers have is a different matter — that is a truncated or early-stopped participant,
    and the analysis has no business averaging over it.
    """
    if not indexed:
        raise ScheduleError("no series supplied")
    sets = {label: set(int(v) for v in idx.tolist()) for label, idx in indexed.items()}
    common = set.intersection(*sets.values())
    if not common:
        raise ScheduleError(
            "the records share no coupling window at all: "
            + "; ".join(
                f"{label} covers {min(s)}..{max(s)} ({len(s)} windows)"
                for label, s in sorted(sets.items())
            )
        )
    span = range(min(common), max(common) + 1)
    holes = {label: sorted(set(span) - s)[:5] for label, s in sets.items() if not set(span) <= s}
    if holes:
        raise ScheduleError(
            "a record is missing coupling windows its peers cover, so the series cannot be "
            "paired window for window: "
            + "; ".join(f"{label} lacks {missing}..." for label, missing in sorted(holes.items()))
            + ". One participant stopped early, or a file is truncated"
        )
    return np.asarray(sorted(common), dtype=np.int64)


def select_windows(
    index: NDArray[np.int64], windows: NDArray[np.int64], *, label: str
) -> NDArray[np.int64]:
    """Row positions of `windows` within `index`, in window order. Fail loud on repeats.

    ``index`` must already be de-duplicated to one row per window (``repeats="last"`` on
    the fluid side, the ``.dat`` reader's own de-duplication on the solid side). A
    repeated window here means the caller handed over a per-ITERATION record and would
    otherwise have silently analysed whichever row ``np.searchsorted`` happened to find.
    """
    positions: dict[int, int] = {}
    for row, window in enumerate(int(v) for v in index.tolist()):
        if window in positions:
            raise ScheduleError(
                f"{label}: coupling window {window} appears more than once. This selector "
                "takes one row per window; de-duplicate the per-iteration record first, "
                "with the rule its cadence classification proved applies"
            )
        positions[window] = row
    return np.asarray([positions[int(w)] for w in windows.tolist()], dtype=np.int64)
