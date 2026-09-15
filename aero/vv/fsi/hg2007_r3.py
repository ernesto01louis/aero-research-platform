"""ADR-045 R3 — the restart-transparency experiment, scored exactly as pre-registered.

The control is the completed Z4 re-probe ``hg2007_flexible_foil-20260912-161321`` (8000/8000
windows); the treatment is the identical submission with one deliberate checkpoint-restart
at window 4000. Four clauses, all required; any one failing means the restart is not
transparent and ADR-041 V7's NO-GO stands:

* **(a)** cycle-averaged lift, thrust and interface power over windows 4001-8000 lie within
  the frozen Q1 bands of the control's same windows — Q1a 2 % on the span mean, Q1b 5 % of
  the control's peak-to-peak in max deviation, reused verbatim and never widened. Amendment
  A10 fixes the single-arm mapping: Q1a applies only to a quantity whose CONTROL mean is
  resolvable against its own peak-to-peak (``|mean| / p2p >= 1``; thrust yes, lift and
  interface power no — a relative band on a near-zero mean is meaningless); Q1b applies to
  all three; Q1c (a two-arm increment) has no single-arm meaning.
* **(b)** the trailing-edge watchpoint difference DECAYS: ``max|Δ|`` over the 200 windows
  after the restart strictly exceeds ``max|Δ|`` over the last 200. A restart may inject a
  transient; it may not inject a shift. Δ is the magnitude of the displacement-vector
  difference. A run identical to the control has no transient and no shift and is read as
  transparent (amendment A11 — the clause exists to refuse a shift).
* **(c)** the ADR-041 divergence detector returns ELIMINATED on the treatment, same grid,
  same bounds.
* **(d)** the IQN-ILS history refills: ``QNColumns`` returns to the control's windows-4001-8000
  mean, and ``Iterations`` to within ±1 of the control's mean, both inside 30 windows of the
  restart. This bounds the one loss a checkpoint cannot fix (R4.3).

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
from typing import Any

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
#: R3(b): the transient window after the restart, and the tail it must have decayed below.
R3_EARLY_WINDOWS = 200
R3_LATE_WINDOWS = 200
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
    windows: list[SolidResidualWindow] = []
    for path, offset in zip(segments.paths, segments.offsets, strict=True):
        series = read_solid_residuals(path)
        for w in series.windows:
            if w.window + offset > (windows[-1].window if windows else 0):
                windows.append(w.model_copy(update={"window": w.window + offset}))
    return SolidResidualSeries(path=segments.paths[-1], windows=tuple(windows))


def _q1_pair(control: NDArray[np.float64], treatment: NDArray[np.float64]) -> dict[str, Any]:
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
        "passed": bool(q1b and (q1a is None or q1a)),
    }


def _aligned(
    a: WindowSeries, b: WindowSeries, first: int, last: int
) -> tuple[NDArray[np.int64], WindowSeries, WindowSeries]:
    sa, sb = a.select(first, last), b.select(first, last)
    common = np.intersect1d(sa.windows, sb.windows)
    expected = last - first + 1
    if common.size != expected:
        raise R3Error(
            f"windows {first}-{last}: the two records share {common.size} of {expected} windows "
            f"(control covers {sa.windows.size}, treatment {sb.windows.size}) — a record is short"
        )
    ia = np.searchsorted(sa.windows, common)
    ib = np.searchsorted(sb.windows, common)
    return (
        common,
        WindowSeries(common, {k: v[ia] for k, v in sa.values.items()}),
        WindowSeries(common, {k: v[ib] for k, v in sb.values.items()}),
    )


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


def score_r3(
    control: R3Inputs,
    treatment: R3Inputs,
    *,
    restart_window: int,
    requested_windows: int,
    early_windows: int = R3_EARLY_WINDOWS,
    late_windows: int = R3_LATE_WINDOWS,
    refill_windows: int = R3_REFILL_WINDOWS,
) -> dict[str, Any]:
    """Evaluate R3(a)-(d). The defaults ARE the pre-registration; tests may shrink them."""
    first, last = restart_window + 1, requested_windows
    # (a) — thrust is -fx, lift is fy, power is the FO's interface power
    a: dict[str, Any] = {}
    _, cf, tf = _aligned(control.forces, treatment.forces, first, last)
    a["thrust"] = _q1_pair(-cf.value("fx"), -tf.value("fx"))
    a["lift"] = _q1_pair(cf.value("fy"), tf.value("fy"))
    _, cp, tp = _aligned(control.power, treatment.power, first, last)
    a["power"] = _q1_pair(cp.value("power"), tp.value("power"))
    a["bands"] = {
        "q1a_span_mean": R3_SPAN_MEAN_BAND,
        "q1b_trace": R3_TRACE_BAND,
        "mean_resolvable_ratio": R3_MEAN_RESOLVABLE_RATIO,
    }
    a["passed"] = all(a[q]["passed"] for q in R3_QUANTITIES)

    # (b) — the trailing-edge displacement difference decays
    _, cw, tw = _aligned(control.watchpoint, treatment.watchpoint, first, last)
    delta = np.hypot(tw.value("d0") - cw.value("d0"), tw.value("d1") - cw.value("d1"))
    windows = cw.windows
    early_mask = windows <= restart_window + early_windows
    late_mask = windows >= requested_windows - late_windows + 1
    early = float(np.max(delta[early_mask])) if early_mask.any() else 0.0
    late = float(np.max(delta[late_mask])) if late_mask.any() else 0.0
    identical = early == 0.0 and late == 0.0
    b = {
        "early_windows": [int(restart_window + 1), int(restart_window + early_windows)],
        "late_windows": [int(requested_windows - late_windows + 1), int(requested_windows)],
        "early_max_abs_delta": early,
        "late_max_abs_delta": late,
        "identical_run_degenerate": identical,
        "passed": bool(early > late or identical),
    }

    # (c) — the detector on the treatment, same grid, same bounds
    report = evaluate_divergence(treatment.residuals)
    completed = treatment.residuals.last_window >= requested_windows
    verdict, why = adr041_rung_verdict(report, completed=completed)
    c = {
        "windows_reached": treatment.residuals.last_window,
        "completed": completed,
        "verdict": verdict,
        "why": why,
        "detector": report.model_dump(mode="json"),
        "passed": verdict == "eliminated",
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

    return {
        "restart_window": restart_window,
        "requested_windows": requested_windows,
        "analysis_windows": [first, last],
        "a": a,
        "b": b,
        "c": c,
        "d": d,
        "passed": bool(a["passed"] and b["passed"] and c["passed"] and d["passed"]),
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
    "R3_ITERATIONS_TOLERANCE",
    "R3_LATE_WINDOWS",
    "R3_MEAN_RESOLVABLE_RATIO",
    "R3_QUANTITIES",
    "R3_REFILL_WINDOWS",
    "R3_SPAN_MEAN_BAND",
    "R3_TRACE_BAND",
    "R3Error",
    "R3Inputs",
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
