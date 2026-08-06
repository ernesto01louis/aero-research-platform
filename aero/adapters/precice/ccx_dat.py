"""Read CalculiX's ``.dat`` reaction-force output, and classify its cadence STRUCTURALLY.

``*NODE PRINT, NSET=..., TOTALS=ONLY`` with ``RF`` writes the summed reaction force at the
prescribed nodes. That is the solid half of the D10 power-closure check: with ``ALPHA=0``
and no damping, the cycle-mean reaction power over the prescribed region equals the
interface power exactly, so the two computed independently must agree — which is what
makes D10 a real check rather than an identity restated.

The format is not a table. Each record is four lines, verified against a live ccx 2.20 run
(the S1 spike)::

    <blank>
     total force (fx,fy,fz) for set NNOSE and time  0.5000000E-02
    <blank>
           -6.391247E-10  6.290534E-06 -7.841086E-16

Two things follow, and both matter.

**The time is printed at seven significant digits.** ``0.5000000E-02`` cannot be compared
bitwise against the coupling schedule's ``dt``; the tolerance here is derived from that
printed precision rather than guessed, and the comparison is to the nearest window index.

**Under IMPLICIT coupling a time appears more than once.** ccx re-does an increment for
every coupling iteration and prints on each, so the record is per-ITERATION rather than
per-window. Which one it is cannot be assumed — it depends on the coupling scheme — so it
is CLASSIFIED, from the coupling iteration counts:

* ``duplicates == 0`` — one row per window, take them as they are;
* ``duplicates == sum(iterations) - n_windows`` — one row per iteration; the converged
  value is the LAST at each time, and the earlier ones are discarded iterates that must
  never be averaged in;
* anything else — RAISE. A partial match means the record does not correspond to the
  coupling log, and quietly picking either rule would produce a plausible number from a
  file we do not understand.

stdlib + numpy only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CcxDatError",
    "ReactionForceHistory",
    "read_reaction_forces",
]

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

#: ccx prints the record time with 7 significant digits. Two windows closer together than
#: this in RELATIVE terms would print identically, which is a real limit on the reader
#: rather than a tolerance anyone chose.
_PRINT_SIGNIFICANT_DIGITS = 7
_TIME_RTOL = 10.0 ** (-(_PRINT_SIGNIFICANT_DIGITS - 1))

_HEADER_RE = re.compile(
    r"^\s*total force \(fx,fy,fz\) for set (?P<nset>\S+) and time\s+(?P<time>\S+)\s*$"
)


class CcxDatError(RuntimeError):
    """A CalculiX ``.dat`` file could not be read, or does not match the coupling record."""


class ReactionForceHistory(BaseModel):
    """Summed reaction forces at a prescribed node set, one row per coupling WINDOW."""

    model_config = _STRICT

    nset: str = Field(..., min_length=1)
    cadence: Literal["per-window", "per-iteration"]
    n_rows_read: int = Field(..., ge=1, description="Records in the file, before de-duplication.")
    n_duplicates: int = Field(..., ge=0, description="Records discarded as superseded iterates.")
    t: tuple[float, ...] = Field(..., min_length=1)
    fx: tuple[float, ...] = Field(..., min_length=1)
    fy: tuple[float, ...] = Field(..., min_length=1)
    fz: tuple[float, ...] = Field(..., min_length=1)

    @property
    def times(self) -> NDArray[np.float64]:
        return np.asarray(self.t, dtype=np.float64)

    @property
    def forces(self) -> NDArray[np.float64]:
        """``(N, 3)`` reaction force. Column 1 is the plunge axis."""
        return np.column_stack(
            [
                np.asarray(self.fx, dtype=np.float64),
                np.asarray(self.fy, dtype=np.float64),
                np.asarray(self.fz, dtype=np.float64),
            ]
        )


def _parse_records(path: Path) -> tuple[str, list[tuple[float, tuple[float, float, float]]]]:
    if not path.is_file():
        raise CcxDatError(f"{path}: CalculiX .dat not found")
    lines = path.read_text(encoding="utf-8").splitlines()
    nsets: set[str] = set()
    records: list[tuple[float, tuple[float, float, float]]] = []
    index = 0
    while index < len(lines):
        match = _HEADER_RE.match(lines[index])
        if match is None:
            index += 1
            continue
        nsets.add(match.group("nset"))
        try:
            time = float(match.group("time"))
        except ValueError as exc:
            raise CcxDatError(
                f"{path}:{index + 1}: unreadable time {match.group('time')!r}"
            ) from exc
        # The values line is the next NON-BLANK line; ccx separates them with a blank.
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines):
            raise CcxDatError(
                f"{path}: the record at t={time!r} has a header but no values — the file is "
                "truncated, which is what a killed solver leaves behind"
            )
        parts = lines[cursor].split()
        if len(parts) != 3:
            raise CcxDatError(
                f"{path}:{cursor + 1}: expected three force components, got {len(parts)}: "
                f"{lines[cursor]!r}"
            )
        try:
            fx, fy, fz = (float(v) for v in parts)
        except ValueError as exc:
            raise CcxDatError(f"{path}:{cursor + 1}: unreadable forces {lines[cursor]!r}") from exc
        records.append((time, (fx, fy, fz)))
        index = cursor + 1

    if not records:
        raise CcxDatError(
            f"{path}: no 'total force' records. The deck needs *NODE PRINT with TOTALS=ONLY "
            "and RF, or the solid produced no reaction output at all"
        )
    if len(nsets) != 1:
        raise CcxDatError(
            f"{path}: records for {len(nsets)} node sets ({sorted(nsets)}); this reader "
            "assumes one prescribed set, and summing across two would be silently wrong"
        )
    return nsets.pop(), records


def read_reaction_forces(
    path: Path,
    *,
    iterations_per_window: NDArray[np.int_] | None = None,
) -> ReactionForceHistory:
    """Read summed reaction forces, classifying the record's cadence structurally.

    `iterations_per_window` is the per-window coupling iteration count from the preCICE
    iterations log. It is what makes the classification a MEASUREMENT: with it, the number
    of duplicate times must equal either zero or exactly ``sum(iterations) - n_windows``,
    and anything between the two is refused. Without it the reader can still de-duplicate,
    but it cannot prove which cadence it saw, so it refuses a record that HAS duplicates
    rather than guessing.
    """
    nset, records = _parse_records(path)
    times = np.asarray([r[0] for r in records], dtype=np.float64)
    forces = np.asarray([r[1] for r in records], dtype=np.float64)

    # Keep the LAST row at each time: under implicit coupling the earlier rows at one time
    # are superseded iterates, and averaging them in would mix unconverged states into a
    # gated statistic.
    unique_times, last_index = _last_occurrence(times)
    n_duplicates = int(times.size - unique_times.size)

    if n_duplicates == 0:
        cadence: Literal["per-window", "per-iteration"] = "per-window"
    else:
        if iterations_per_window is None:
            raise CcxDatError(
                f"{path}: {n_duplicates} duplicate time(s) in the record, but no coupling "
                "iteration counts were supplied to classify the cadence. A per-iteration "
                "record de-duplicated on a guess is a plausible number from a file we do "
                "not understand — pass the iterations log."
            )
        iterations = np.asarray(iterations_per_window, dtype=np.int64)
        expected = int(iterations.sum() - iterations.size)
        if n_duplicates != expected:
            raise CcxDatError(
                f"{path}: {n_duplicates} duplicate time(s), but the coupling log implies "
                f"{expected} (sum(iterations)={int(iterations.sum())} over "
                f"{iterations.size} windows). The .dat and the iterations log do not "
                "describe the same run — neither de-duplication rule applies, and picking "
                "one would produce a number from a record that is not understood."
            )
        if unique_times.size != iterations.size:
            raise CcxDatError(
                f"{path}: {unique_times.size} distinct times but {iterations.size} coupled "
                "windows in the log — the solid and the coupling disagree about how many "
                "windows ran"
            )
        cadence = "per-iteration"

    kept = forces[last_index]
    return ReactionForceHistory(
        nset=nset,
        cadence=cadence,
        n_rows_read=int(times.size),
        n_duplicates=n_duplicates,
        t=tuple(float(v) for v in unique_times),
        fx=tuple(float(v) for v in kept[:, 0]),
        fy=tuple(float(v) for v in kept[:, 1]),
        fz=tuple(float(v) for v in kept[:, 2]),
    )


def _last_occurrence(times: NDArray[np.float64]) -> tuple[NDArray[np.float64], NDArray[np.int_]]:
    """Distinct times in order, and the index of the LAST record at each.

    Equality is exact here on purpose: ccx prints one time to a fixed number of digits, so
    two rows for the same window carry the same STRING and therefore the same float. The
    print-precision tolerance belongs to comparisons against the coupling schedule
    (:func:`assert_matches_schedule`), not to grouping rows that came out of one file.
    """
    keep: dict[float, int] = {}
    for index, value in enumerate(times):
        keep[float(value)] = index
    ordered = sorted(keep)
    return np.asarray(ordered, dtype=np.float64), np.asarray(
        [keep[value] for value in ordered], dtype=np.int64
    )


def assert_matches_schedule(
    history: ReactionForceHistory,
    *,
    time_window_size: float,
    n_windows: int,
) -> None:
    """Refuse unless the record's times ARE the coupling schedule, to printed precision.

    The comparison is to the nearest window index rather than value-by-value, because the
    printed time carries seven significant digits and the schedule does not: a record can
    be exactly right and still not compare equal as a float.
    """
    times = history.times
    if times.size != n_windows:
        raise CcxDatError(
            f"the solid recorded {times.size} windows, the coupling ran {n_windows}. A "
            "short solid record means ccx stopped early -- check *STEP INC, which at "
            "CalculiX's default of 100 ends the step mid-run with exit code ZERO."
        )
    index = np.rint(times / time_window_size)
    expected = index * time_window_size
    worst = float(np.max(np.abs(times - expected)))
    allowed = _TIME_RTOL * float(np.max(np.abs(times)))
    if worst > allowed:
        raise CcxDatError(
            f"the solid's record times are not the coupling schedule: worst deviation "
            f"{worst:.3e} s against {allowed:.3e} s allowed by the printed precision "
            f"({_PRINT_SIGNIFICANT_DIGITS} significant digits). The solid stepped at a "
            "different dt than the coupling window."
        )
    if not np.array_equal(index, np.arange(1, n_windows + 1)):
        raise CcxDatError(
            "the solid's record skips or repeats a window: its times do not map onto "
            "consecutive window indices"
        )
