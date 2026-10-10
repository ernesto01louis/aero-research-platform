"""ADR-045 R3 — the restart-transparency experiment, scored exactly as pre-registered.

The control is the completed Z4 re-probe ``hg2007_flexible_foil-20260912-161321`` (8000/8000
windows); the treatment is the identical submission with one deliberate checkpoint-restart
at window 4000. Four clauses, all required; any one failing means the restart is not
transparent and ADR-041 V7's NO-GO stands:

* **(a) as accepted (amendment A17, option 2 of handoff §6.82).** Two draws of the identical
  submission — D-C1 and its re-probe, the control — differ over windows 4001-8000 by 35 %
  (thrust) and 51 % (lift) of the control's peak-to-peak, so the Q1b band as written cannot
  be passed by any treatment. A restart is therefore transparent when the restarted run is
  INDISTINGUISHABLE FROM ANOTHER FRESH DRAW: per quantity (thrust, lift, interface power),
  the treatment's RMS deviation from the control over windows 4001-8000 is within
  ``R3_YARDSTICK_FACTOR`` (2x) of the reference draw's RMS deviation from the control, and
  its span-mean difference within the larger of Q1a's 2 % of the control mean and 2x the
  reference draw's span-mean difference. The factor is stated before the treatment exists.
  The as-written Q1a/Q1b numbers are still computed and recorded, informationally.
* **(b) as accepted (A17).** No shift beyond draw noise: over the last 200 windows the
  treatment's RMS trailing-edge displacement difference from the control is within 2x the
  reference draw's. The early-window transient is recorded, not gated. Δ is the magnitude
  of the displacement-vector difference.
* **(c)** the ADR-041 divergence detector returns ELIMINATED on the treatment, same grid,
  same bounds.
* **(d)** the IQN-ILS history refills: ``QNColumns`` returns to the control's windows-4001-8000
  mean, and ``Iterations`` to within ±1 of the control's mean, both inside 30 windows of the
  restart. This bounds the one loss a checkpoint cannot fix (R4.3).
* **(e) the episode rule, decided before the run (A17).** The two reference draws differ by
  a ~1e-5 N floor everywhere plus two localised bursts of 1-2e-3 N (windows 201-400 and
  ~1376). If (a) fails ONLY because of one such isolated episode far from the restart —
  exactly one contiguous span (gaps under ``R3_EPISODE_GAP`` windows merged) of windows
  where the treatment's deviation exceeds ``R3_EPISODE_FACTOR`` (10x) the reference RMS,
  at most ``R3_EPISODE_MAX_WINDOWS`` (400) long, starting at least ``R3_EPISODE_CLEARANCE``
  (1000) windows after the restart and not touching the late window, and (a) passes with
  that span excised from BOTH deviations — the verdict is ``inconclusive-episode``, not a
  pass and not a fail: the episode is indistinguishable from the draw noise the reference
  pair shows, and the test cannot attribute it. Exactly one re-probe is then permitted (the
  ADR-041 V1(b) pattern); a second ``inconclusive-episode`` is UNRESOLVED and the NO-GO
  stands. Anything else that fails (a) or (b) is a ``fail``.

**The limit of what a pass says (A17).** R3 runs at 1.3-3.3 % of the full plunge amplitude
(windows 4000-8000 of a 50 700-window cycle, inside the first sixth of the startup ramp). A
pass is evidence that a restart is transparent THERE; it is not evidence about restarts in
settled full-amplitude cycles, and the ADR does not claim it is.

A restarted run is several SEGMENTS: the launcher rotates every log to ``<stem>.seg<n>.<ext>``
before a relaunch (amendment A8), preCICE's ``TimeWindow`` and watch-point ``Time`` restart
at zero in a fresh instance, and OpenFOAM writes a new ``postProcessing/forces1/<startTime>``
directory. This module joins the segments on GLOBAL window indices using the restart
windows the submission record carries (amendment A9). Everything is stdlib + numpy +
pydantic-free arrays (Invariant 1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from aero.adapters.openfoam.flexible_foil import read_interface_power
from aero.adapters.openfoam.force_io import read_force_history
from aero.adapters.precice.logs import (
    SolidResidualSeries,
    SolidResidualWindow,
    evaluate_divergence,
    read_iterations_log,
    read_solid_residuals,
)
from aero.adapters.precice.schedule import StampConvention, window_indices
from aero.adapters.precice.watchpoint import read_watchpoint
from aero.vv.fsi.hg2007_flexible_foil import adr041_rung_verdict

#: ADR-040 Q1a and Q1b, verbatim (ADR-045 R3(a): "reused verbatim and not widened").
R3_SPAN_MEAN_BAND = 0.02
R3_TRACE_BAND = 0.05
#: A10: Q1a's relative span-mean band applies only where the CONTROL's |mean| is at least
#: its own peak-to-peak. Measured on the control over windows 4001-8000: thrust 1.48,
#: lift 0.017, interface power 0.023.
R3_MEAN_RESOLVABLE_RATIO = 1.0
#: R3(b): the transient window after the restart (recorded), and the late window (gated).
R3_EARLY_WINDOWS = 200
R3_LATE_WINDOWS = 200
#: A17: the two-draw yardstick. A restart that doubles the natural run-to-run scatter is a
#: shift; stated before the treatment exists, never tuned to a result.
R3_YARDSTICK_FACTOR = 2.0
#: A17 (e): an isolated episode is a single span of windows over this multiple of the
#: reference RMS, merged across gaps shorter than R3_EPISODE_GAP, at most
#: R3_EPISODE_MAX_WINDOWS long, starting at least R3_EPISODE_CLEARANCE windows after the
#: restart, not touching the late window.
R3_EPISODE_FACTOR = 10.0
R3_EPISODE_GAP = 50
R3_EPISODE_MAX_WINDOWS = 400
R3_EPISODE_CLEARANCE = 1000
#: R3(d): the refill deadline after the restart, and the Iterations tolerance.
R3_REFILL_WINDOWS = 30
R3_ITERATIONS_TOLERANCE = 1.0
#: The coupling's configured cap (the template's max-iterations).
PRECICE_MAX_ITERATIONS = 50
TE_WATCHPOINT = "Trailing-Edge"
SOLID_PARTICIPANT = "Solid"
SOLID_DIRNAME = "solid-calculix"
FLUID_DIRNAME = "fluid-openfoam"
EXCHANGE_GLOB = "hg2007-*-foil"
#: The fluid function objects stamp the window START (``aero.vv.fsi.hg2007_readout``).
FLUID_STAMP: StampConvention = "window-start"
#: The R3 quantities and the force.dat column each is read from.
R3_QUANTITIES = ("thrust", "lift", "power")


class R3Error(RuntimeError):
    """A record needed by R3 is missing, ambiguous or inconsistent."""


@dataclass(frozen=True)
class Segments:
    """A rotated log's files, oldest first, with the global window each one starts after."""

    paths: tuple[Path, ...]
    offsets: tuple[int, ...]


def segment_files(
    directory: Path, stem: str, suffix: str, *, restart_windows: Sequence[int]
) -> Segments:
    """``<stem>.seg1.<suffix>`` … then ``<stem>.<suffix>`` (the live/final segment).

    The count must match the restarts the record carries: one more file than restarts.
    A mismatch is a rotation that did not happen or a restart that was not recorded, and
    either way the join would be a guess.
    """
    paths: list[Path] = []
    k = 1
    while (directory / f"{stem}.seg{k}.{suffix}").is_file():
        paths.append(directory / f"{stem}.seg{k}.{suffix}")
        k += 1
    final = directory / f"{stem}.{suffix}"
    if not final.is_file():
        raise R3Error(f"{final}: missing")
    paths.append(final)
    if len(paths) != len(restart_windows) + 1:
        raise R3Error(
            f"{directory}/{stem}: {len(paths)} segment file(s) but {len(restart_windows)} "
            f"restart(s) recorded ({list(restart_windows)}) — a rotation or a record is missing"
        )
    return Segments(tuple(paths), (0, *(int(w) for w in restart_windows)))


@dataclass(frozen=True)
class WindowSeries:
    """Per-window values on GLOBAL window indices, one row per window."""

    windows: NDArray[np.int64]
    values: dict[str, NDArray[np.float64]]

    def select(self, first: int, last: int) -> WindowSeries:
        keep = (self.windows >= first) & (self.windows <= last)
        return WindowSeries(self.windows[keep], {k: v[keep] for k, v in self.values.items()})

    def value(self, name: str) -> NDArray[np.float64]:
        return self.values[name]

    @property
    def last_window(self) -> int:
        return int(self.windows[-1]) if self.windows.size else 0


def _merge(
    parts: Sequence[tuple[NDArray[np.int64], dict[str, NDArray[np.float64]]]],
) -> WindowSeries:
    """Concatenate segments; a window present in two keeps the LATER segment's row."""
    if not parts:
        raise R3Error("no segments to merge")
    names = list(parts[0][1])
    rows: dict[int, dict[str, float]] = {}
    for windows, values in parts:
        for i, w in enumerate(int(v) for v in windows.tolist()):
            rows[w] = {name: float(values[name][i]) for name in names}
    ordered = sorted(rows)
    return WindowSeries(
        np.asarray(ordered, dtype=np.int64),
        {name: np.asarray([rows[w][name] for w in ordered], dtype=np.float64) for name in names},
    )


def _exchange_dir(case_root: Path) -> Path:
    matches = sorted(case_root.glob(EXCHANGE_GLOB))
    if len(matches) != 1:
        raise R3Error(f"{case_root}: expected one {EXCHANGE_GLOB} directory, found {len(matches)}")
    return matches[0]


def read_r3_forces(case_root: Path, *, dt: float) -> WindowSeries:
    """Thrust-axis and lift-axis interface force per window, across every restart segment.

    OpenFOAM opens ``postProcessing/forces1/<startTime>/force.dat`` per (re)start; the
    time stamps are absolute, so segments join on the window index directly and the later
    segment wins the boundary row.
    """
    fluid_dir = _exchange_dir(case_root) / FLUID_DIRNAME
    files = sorted(
        fluid_dir.glob("postProcessing/forces1/*/force.dat"), key=lambda p: float(p.parent.name)
    )
    if not files:
        raise R3Error(f"{fluid_dir}: no postProcessing/forces1/*/force.dat")
    parts = []
    for path in files:
        forces = read_force_history(path, repeats="last")
        index = window_indices(forces.t, time_window_size=dt, stamp=FLUID_STAMP, label=str(path))
        total = forces.pressure + forces.viscous
        parts.append((index, {"fx": total[:, 0], "fy": total[:, 1]}))
    return _merge(parts)


def read_r3_power(case_root: Path, *, dt: float, restart_windows: Sequence[int]) -> WindowSeries:
    """The coded function object's interface power per window, across ``Fluid.seg*.log``."""
    segments = segment_files(case_root, "Fluid", "log", restart_windows=restart_windows)
    parts = []
    for path in segments.paths:
        history = read_interface_power(path, repeats="last")
        index = window_indices(history.t, time_window_size=dt, stamp=FLUID_STAMP, label=str(path))
        parts.append((index, {"power": history.power}))
    return _merge(parts)


def read_r3_watchpoint(
    case_root: Path, *, dt: float, restart_windows: Sequence[int]
) -> WindowSeries:
    """The trailing-edge displacement per window, across the rotated watch-point logs.

    preCICE stamps a row per COMPLETED window at ``Time = k * dt`` from ITS OWN zero, which
    restarts with the instance; the segment's offset turns ``k`` into the global window. The
    ``Time = 0`` row (the initial or restored state) is dropped from every segment.
    """
    solid_dir = _exchange_dir(case_root) / SOLID_DIRNAME
    segments = segment_files(
        solid_dir,
        f"precice-{SOLID_PARTICIPANT}-watchpoint-{TE_WATCHPOINT}",
        "log",
        restart_windows=restart_windows,
    )
    parts = []
    for path, offset in zip(segments.paths, segments.offsets, strict=True):
        trace = read_watchpoint(path, participant=SOLID_PARTICIPANT, watch_point=TE_WATCHPOINT)
        local = np.rint(np.asarray(trace.t, dtype=np.float64) / dt).astype(np.int64)
        keep = local >= 1
        parts.append(
            (
                local[keep] + offset,
                {
                    "d0": np.asarray(trace.values["Displacement0"], dtype=np.float64)[keep],
                    "d1": np.asarray(trace.values["Displacement1"], dtype=np.float64)[keep],
                },
            )
        )
    return _merge(parts)


def read_r3_iterations(case_root: Path, *, restart_windows: Sequence[int]) -> WindowSeries:
    """``Iterations`` and ``QNColumns`` per global window, across the rotated iteration logs."""
    solid_dir = _exchange_dir(case_root) / SOLID_DIRNAME
    segments = segment_files(
        solid_dir, f"precice-{SOLID_PARTICIPANT}-iterations", "log", restart_windows=restart_windows
    )
    parts = []
    for path, offset in zip(segments.paths, segments.offsets, strict=True):
        report = read_iterations_log(
            path, participant=SOLID_PARTICIPANT, max_iterations_configured=PRECICE_MAX_ITERATIONS
        )
        if any("QNColumns" not in w.quasi_newton for w in report.windows):
            raise R3Error(f"{path}: no QNColumns column — R3(d) measures the history depth itself")
        parts.append(
            (
                np.asarray([w.time_window + offset for w in report.windows], dtype=np.int64),
                {
                    "iterations": np.asarray(
                        [w.iterations for w in report.windows], dtype=np.float64
                    ),
                    "qn": np.asarray(
                        [w.quasi_newton["QNColumns"] for w in report.windows], dtype=np.float64
                    ),
                },
            )
        )
    return _merge(parts)


def read_r3_residuals(case_root: Path, *, restart_windows: Sequence[int]) -> SolidResidualSeries:
    """The ADR-041 detector's input across the rotated ``Solid.log`` segments, on global windows."""
    segments = segment_files(case_root, "Solid", "log", restart_windows=restart_windows)
    by_window: dict[int, SolidResidualWindow] = {}
    for path, offset in zip(segments.paths, segments.offsets, strict=True):
        series = read_solid_residuals(path)
        for w in series.windows:
            # A segment stopped deliberately AFTER its checkpoint carries windows the next
            # segment recomputes; the later segment wins those, like every other record.
            by_window[w.window + offset] = w.model_copy(update={"window": w.window + offset})
    ordered = tuple(by_window[k] for k in sorted(by_window))
    return SolidResidualSeries(path=segments.paths[-1], windows=ordered)


def _q1_pair(control: NDArray[np.float64], treatment: NDArray[np.float64]) -> dict[str, Any]:
    """The as-written Q1a/Q1b numbers (A10 mapping), recorded informationally under A17."""
    mean_c, mean_t = float(np.mean(control)), float(np.mean(treatment))
    p2p = float(np.max(control) - np.min(control))
    span_rel = abs(mean_t - mean_c) / max(abs(mean_c), 1e-300)
    trace = float(np.max(np.abs(treatment - control))) / max(p2p, 1e-300)
    resolvable = abs(mean_c) / max(p2p, 1e-300)
    applicable = resolvable >= R3_MEAN_RESOLVABLE_RATIO
    q1a = bool(span_rel <= R3_SPAN_MEAN_BAND) if applicable else None
    q1b = bool(trace <= R3_TRACE_BAND)
    return {
        "n_windows": int(control.size),
        "control_mean": mean_c,
        "treatment_mean": mean_t,
        "span_mean_relative_difference": span_rel,
        "control_peak_to_peak": p2p,
        "max_absolute_deviation": float(np.max(np.abs(treatment - control))),
        "trace_deviation_over_amplitude": trace,
        "control_mean_over_peak_to_peak": resolvable,
        "q1a_applicable": applicable,
        "q1a_within_band": q1a,
        "q1b_within_band": q1b,
        "as_written_passed": bool(q1b and (q1a is None or q1a)),
    }


def _rms(values: NDArray[np.float64]) -> float:
    return float(np.sqrt(np.mean(np.square(values)))) if values.size else 0.0


def _yardstick(
    control: NDArray[np.float64],
    treatment: NDArray[np.float64],
    reference: NDArray[np.float64],
    *,
    exclude: NDArray[np.bool_] | None = None,
) -> dict[str, Any]:
    """A17 (a): the treatment against the two-draw yardstick, per quantity."""
    keep = np.ones(control.shape, dtype=bool) if exclude is None else ~exclude
    dev_t = (treatment - control)[keep]
    dev_r = (reference - control)[keep]
    rms_t, rms_r = _rms(dev_t), _rms(dev_r)
    mean_c = float(np.mean(control[keep]))
    span_t = abs(float(np.mean(treatment[keep])) - mean_c)
    span_r = abs(float(np.mean(reference[keep])) - mean_c)
    span_limit = max(R3_SPAN_MEAN_BAND * abs(mean_c), R3_YARDSTICK_FACTOR * span_r)
    rms_ok = bool(rms_t <= R3_YARDSTICK_FACTOR * rms_r)
    span_ok = bool(span_t <= span_limit)
    return {
        "n_windows": int(keep.sum()),
        "treatment_rms_deviation": rms_t,
        "reference_rms_deviation": rms_r,
        "rms_ratio": rms_t / max(rms_r, 1e-300),
        "rms_within_factor": rms_ok,
        "treatment_span_mean_difference": span_t,
        "reference_span_mean_difference": span_r,
        "span_mean_limit": span_limit,
        "span_mean_within_limit": span_ok,
        "passed": rms_ok and span_ok,
    }


def _episode_spans(exceed: NDArray[np.bool_], windows: NDArray[np.int64]) -> list[tuple[int, int]]:
    """Contiguous spans of exceeding windows, gaps shorter than R3_EPISODE_GAP merged."""
    spans: list[tuple[int, int]] = []
    for w in windows[exceed].tolist():
        if spans and w - spans[-1][1] < R3_EPISODE_GAP:
            spans[-1] = (spans[-1][0], int(w))
        else:
            spans.append((int(w), int(w)))
    return spans


def _aligned(
    a: WindowSeries, b: WindowSeries, first: int, last: int
) -> tuple[NDArray[np.int64], WindowSeries, WindowSeries]:
    sa, sb = a.select(first, last), b.select(first, last)
    common = np.intersect1d(sa.windows, sb.windows)
    expected = last - first + 1
    if common.size != expected:
        raise R3Error(
            f"windows {first}-{last}: the two records share {common.size} of {expected} windows "
            f"(control covers {sa.windows.size}, treatment {sb.windows.size}) -- a record is short"
        )
    ia = np.searchsorted(sa.windows, common)
    ib = np.searchsorted(sb.windows, common)
    return (
        common,
        WindowSeries(common, {k: v[ia] for k, v in sa.values.items()}),
        WindowSeries(common, {k: v[ib] for k, v in sb.values.items()}),
    )


def _aligned3(
    a: WindowSeries, b: WindowSeries, c: WindowSeries, first: int, last: int
) -> tuple[NDArray[np.int64], WindowSeries, WindowSeries, WindowSeries]:
    windows, sa, sb = _aligned(a, b, first, last)
    _, _, sc = _aligned(a, c, first, last)
    if not np.array_equal(sc.windows, windows):
        raise R3Error(f"windows {first}-{last}: the reference draw does not cover the same windows")
    return windows, sa, sb, sc


@dataclass(frozen=True)
class R3Inputs:
    """Everything a run contributes to R3, read once."""

    forces: WindowSeries
    power: WindowSeries
    watchpoint: WindowSeries
    iterations: WindowSeries
    residuals: SolidResidualSeries


def read_r3_inputs(case_root: Path, *, dt: float, restart_windows: Sequence[int]) -> R3Inputs:
    return R3Inputs(
        forces=read_r3_forces(case_root, dt=dt),
        power=read_r3_power(case_root, dt=dt, restart_windows=restart_windows),
        watchpoint=read_r3_watchpoint(case_root, dt=dt, restart_windows=restart_windows),
        iterations=read_r3_iterations(case_root, restart_windows=restart_windows),
        residuals=read_r3_residuals(case_root, restart_windows=restart_windows),
    )


R3Verdict = Literal["pass", "fail", "inconclusive-episode"]


def score_r3(
    control: R3Inputs,
    treatment: R3Inputs,
    *,
    reference: R3Inputs,
    restart_window: int,
    requested_windows: int,
    early_windows: int = R3_EARLY_WINDOWS,
    late_windows: int = R3_LATE_WINDOWS,
    refill_windows: int = R3_REFILL_WINDOWS,
    episode_clearance: int = R3_EPISODE_CLEARANCE,
    episode_max_windows: int = R3_EPISODE_MAX_WINDOWS,
) -> dict[str, Any]:
    """Evaluate R3(a)-(e) as accepted (A17). The defaults ARE the pre-registration; tests
    may shrink the window lengths, never the factors."""
    first, last = restart_window + 1, requested_windows
    late_first = requested_windows - late_windows + 1

    # (a) — the two-draw yardstick per quantity; the as-written Q1 numbers ride along
    series = {
        "thrust": (control.forces, treatment.forces, reference.forces, "fx", -1.0),
        "lift": (control.forces, treatment.forces, reference.forces, "fy", 1.0),
        "power": (control.power, treatment.power, reference.power, "power", 1.0),
    }
    a: dict[str, Any] = {}
    excised: dict[str, NDArray[np.bool_]] = {}
    episodes: dict[str, Any] = {}
    for name, (cs, ts, rs, col, sign) in series.items():
        windows, ca, ta, ra = _aligned3(cs, ts, rs, first, last)
        cv, tv, rv = sign * ca.value(col), sign * ta.value(col), sign * ra.value(col)
        row = _yardstick(cv, tv, rv)
        row["as_written"] = _q1_pair(cv, tv)
        # (e) candidate episodes: windows where the treatment's deviation exceeds
        # R3_EPISODE_FACTOR x the reference RMS
        rms_r = row["reference_rms_deviation"]
        exceed = np.abs(tv - cv) > R3_EPISODE_FACTOR * max(rms_r, 1e-300)
        spans = _episode_spans(exceed, windows)
        isolated = (
            len(spans) == 1
            and spans[0][1] - spans[0][0] + 1 <= episode_max_windows
            and spans[0][0] >= restart_window + episode_clearance
            and spans[0][1] < late_first
        )
        episodes[name] = {
            "spans": spans,
            "isolated": bool(isolated),
            "threshold": R3_EPISODE_FACTOR * rms_r,
        }
        if isolated:
            lo, hi = spans[0]
            mask = (windows >= lo) & (windows <= hi)
            excised[name] = mask
            row["with_episode_excised"] = _yardstick(cv, tv, rv, exclude=mask)
        a[name] = row
    a["yardstick_factor"] = R3_YARDSTICK_FACTOR
    a["passed"] = all(a[q]["passed"] for q in R3_QUANTITIES)

    # (b) — no shift beyond draw noise in the late window; the early transient recorded
    windows, cw, tw, rw = _aligned3(
        control.watchpoint, treatment.watchpoint, reference.watchpoint, first, last
    )
    delta_t = np.hypot(tw.value("d0") - cw.value("d0"), tw.value("d1") - cw.value("d1"))
    delta_r = np.hypot(rw.value("d0") - cw.value("d0"), rw.value("d1") - cw.value("d1"))
    early_mask = windows <= restart_window + early_windows
    late_mask = windows >= late_first
    late_t, late_r = _rms(delta_t[late_mask]), _rms(delta_r[late_mask])
    b = {
        "early_windows": [int(first), int(restart_window + early_windows)],
        "late_windows": [int(late_first), int(requested_windows)],
        "early_max_abs_delta": float(np.max(delta_t[early_mask])) if early_mask.any() else 0.0,
        "early_reference_max_abs_delta": float(np.max(delta_r[early_mask]))
        if early_mask.any()
        else 0.0,
        "late_rms_delta": late_t,
        "late_reference_rms_delta": late_r,
        "late_rms_ratio": late_t / max(late_r, 1e-300),
        "passed": bool(late_t <= R3_YARDSTICK_FACTOR * late_r),
    }

    # (c) — the detector on the treatment, same grid, same bounds
    report = evaluate_divergence(treatment.residuals)
    completed = treatment.residuals.last_window >= requested_windows
    verdict_c, why_c = adr041_rung_verdict(report, completed=completed)
    c = {
        "windows_reached": treatment.residuals.last_window,
        "completed": completed,
        "verdict": verdict_c,
        "why": why_c,
        "detector": report.model_dump(mode="json"),
        "passed": verdict_c == "eliminated",
    }

    # (d) — the IQN-ILS history refills
    ci = control.iterations.select(first, last)
    if ci.windows.size == 0:
        raise R3Error("the control has no iteration rows in the analysis window")
    mean_qn = float(np.mean(ci.value("qn")))
    mean_it = float(np.mean(ci.value("iterations")))
    ti = treatment.iterations.select(first, last)
    refilled = None
    for w, qn, it in zip(
        ti.windows.tolist(), ti.value("qn").tolist(), ti.value("iterations").tolist(), strict=True
    ):
        if qn >= mean_qn and abs(it - mean_it) <= R3_ITERATIONS_TOLERANCE:
            refilled = int(w)
            break
    deadline = restart_window + refill_windows
    d = {
        "control_mean_qn_columns": mean_qn,
        "control_mean_iterations": mean_it,
        "iterations_tolerance": R3_ITERATIONS_TOLERANCE,
        "refilled_at_window": refilled,
        "deadline_window": deadline,
        "passed": bool(refilled is not None and refilled <= deadline),
    }

    # (e) — the episode rule: (a) failing ONLY through one isolated episode far from the
    # restart, passing with it excised, with (b)-(d) passing, is inconclusive, not a fail
    failing = [q for q in R3_QUANTITIES if not a[q]["passed"]]
    episode_only = bool(
        failing
        and all(q in excised and a[q]["with_episode_excised"]["passed"] for q in failing)
        and all(a[q]["passed"] or q in excised for q in R3_QUANTITIES)
    )
    if a["passed"] and b["passed"] and c["passed"] and d["passed"]:
        verdict: R3Verdict = "pass"
    elif episode_only and b["passed"] and c["passed"] and d["passed"]:
        verdict = "inconclusive-episode"
    else:
        verdict = "fail"
    e = {
        "episodes": episodes,
        "failing_quantities": failing,
        "episode_only": episode_only,
        "rule": {
            "factor_over_reference_rms": R3_EPISODE_FACTOR,
            "merge_gap_windows": R3_EPISODE_GAP,
            "max_windows": episode_max_windows,
            "clearance_after_restart": episode_clearance,
        },
    }

    return {
        "restart_window": restart_window,
        "requested_windows": requested_windows,
        "analysis_windows": [first, last],
        "a": a,
        "b": b,
        "c": c,
        "d": d,
        "e": e,
        "verdict": verdict,
        "passed": verdict == "pass",
    }


def two_draw_context(
    control: R3Inputs,
    other: R3Inputs,
    *,
    restart_window: int,
    requested_windows: int,
    early_windows: int = R3_EARLY_WINDOWS,
    late_windows: int = R3_LATE_WINDOWS,
) -> dict[str, Any]:
    """What determinism alone does to (a) and (b): another completed draw against the control.

    Context, never a clause — it tells a reader whether a (b) failure could be the two
    draws drifting apart rather than the restart.
    """
    first, last = restart_window + 1, requested_windows
    out: dict[str, Any] = {}
    _, cf, of = _aligned(control.forces, other.forces, first, last)
    out["thrust"] = _q1_pair(-cf.value("fx"), -of.value("fx"))
    out["lift"] = _q1_pair(cf.value("fy"), of.value("fy"))
    _, cw, ow = _aligned(control.watchpoint, other.watchpoint, first, last)
    delta = np.hypot(ow.value("d0") - cw.value("d0"), ow.value("d1") - cw.value("d1"))
    windows = cw.windows
    out["early_max_abs_delta"] = float(np.max(delta[windows <= restart_window + early_windows]))
    out["late_max_abs_delta"] = float(
        np.max(delta[windows >= requested_windows - late_windows + 1])
    )
    return out


__all__ = [
    "PRECICE_MAX_ITERATIONS",
    "R3_EARLY_WINDOWS",
    "R3_EPISODE_CLEARANCE",
    "R3_EPISODE_FACTOR",
    "R3_EPISODE_GAP",
    "R3_EPISODE_MAX_WINDOWS",
    "R3_ITERATIONS_TOLERANCE",
    "R3_LATE_WINDOWS",
    "R3_MEAN_RESOLVABLE_RATIO",
    "R3_QUANTITIES",
    "R3_REFILL_WINDOWS",
    "R3_SPAN_MEAN_BAND",
    "R3_TRACE_BAND",
    "R3_YARDSTICK_FACTOR",
    "R3Error",
    "R3Inputs",
    "R3Verdict",
    "Segments",
    "WindowSeries",
    "read_r3_forces",
    "read_r3_inputs",
    "read_r3_iterations",
    "read_r3_power",
    "read_r3_residuals",
    "read_r3_watchpoint",
    "score_r3",
    "segment_files",
    "two_draw_context",
]
