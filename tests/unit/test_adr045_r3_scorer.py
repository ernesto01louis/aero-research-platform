"""ADR-045 R3, scored by code fixed before the treatment exists.

The four clauses, their bands and their windows are module constants; the tests below drive
synthetic control/treatment pairs through them (shrunken windows, same rules) so every
clause has a passing and a failing fixture, and the segment join that a restarted run
needs is exercised on rotated logs with preCICE-local numbering. A gated test scores the
REAL control against itself when the NFS share is mounted: the scorer's calibration, which
must read as transparent (identical run) and which fixes A10's applicability from the
control's own numbers -- Q1a applies to thrust only.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from aero.vv.fsi.hg2007_r3 import (
    R3_EARLY_WINDOWS,
    R3_LATE_WINDOWS,
    R3_REFILL_WINDOWS,
    R3_SPAN_MEAN_BAND,
    R3_TRACE_BAND,
    R3Error,
    read_r3_inputs,
    score_r3,
    segment_files,
    two_draw_context,
)

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
DT = 2e-5
N = 1400  # windows: enough for the ADR-041 grid to be discriminating (>= 50 % active chunks)
R = 400  # the synthetic restart window


def _driver():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


# --- a synthetic coupled run, optionally split into two segments at R ---------------------

Signal = Callable[[int], float]


def _control_signals() -> dict[str, Signal]:
    return {
        "fx": lambda w: -1.0e-3 - 1.0e-5 * math.sin(w / 7.0),  # thrust: resolvable mean
        "fy": lambda w: 1.0e-2 * math.sin(w / 5.0),  # lift: near-zero mean
        "power": lambda w: 2.0e-5 * math.sin(w / 5.0 + 0.3),  # power: near-zero mean
        "d0": lambda w: 1.0e-6 * math.sin(w / 11.0),
        "d1": lambda w: 5.0e-5 * math.sin(w / 5.0),
        "resid": lambda w: 5.0,  # active and flat: the detector reads CLEAN
        "iterations": lambda w: 4.0,
        "qn": lambda w: 50.0,
    }


def _write_run(root: Path, signals: dict[str, Signal], *, split_at: int | None) -> None:
    """Write force.dat, Fluid.log, the watch-point, the iterations log and Solid.log.

    With ``split_at`` the run is written as two segments the way the launcher leaves them
    after a relaunch (A8): ``*.seg1.*`` for windows 1..split_at, the plain name for the
    rest with preCICE-local numbering, and a second ``postProcessing/forces1/<t>`` dir.
    """
    tutorial = root / "tutorial"
    solid = tutorial / "hg2007-flexible-foil" / "solid-calculix"
    fluid = tutorial / "hg2007-flexible-foil" / "fluid-openfoam"
    solid.mkdir(parents=True)
    fluid.mkdir(parents=True)
    segments = [(1, N, 0)] if split_at is None else [(1, split_at, 0), (split_at + 1, N, split_at)]
    for k, (first, last, offset) in enumerate(segments, start=1):
        final = k == len(segments)
        tag = "" if final else f".seg{k}"
        # force.dat: fluid stamps the window START; one trailing row at the segment's end
        start_t = (first - 1) * DT
        fdir = fluid / "postProcessing" / "forces1" / f"{start_t:.12g}"
        fdir.mkdir(parents=True)
        rows = [
            "# Force",
            "# Time total_x total_y total_z pressure_x pressure_y pressure_z viscous_x viscous_y viscous_z",
        ]
        for w in range(first, last + 2):
            t = (w - 1) * DT
            ww = min(w, N)
            rows.append(
                f"{t:.12g} {signals['fx'](ww):.12e} {signals['fy'](ww):.12e} 0 0 0 0 {signals['fx'](ww):.12e} {signals['fy'](ww):.12e} 0"
            )
        (fdir / "force.dat").write_text("\n".join(rows) + "\n", encoding="utf-8")
        # Fluid.log: the interface-power FO, window-start stamps
        (tutorial / f"Fluid{tag}.log").write_text(
            "".join(
                f"aeroInterfacePower {(w - 1) * DT:.12g} {signals['power'](min(w, N)):.12e} 0 0\n"
                for w in range(first, last + 2)
            ),
            encoding="utf-8",
        )
        # watch-point: preCICE-local Time = k*dt, a Time=0 row first
        wp = [
            "  Time  Coordinate0  Coordinate1  Displacement0  Displacement1  Force0  Force1",
            " 0.0 0.09 0.0 0.0 0.0 0.0 0.0",
        ]
        for w in range(first, last + 1):
            wp.append(
                f" {(w - offset) * DT:.12e} 0.09 0.0 {signals['d0'](w):.12e} {signals['d1'](w):.12e} 0.0 0.0"
            )
        (solid / f"precice-Solid-watchpoint-Trailing-Edge{tag}.log").write_text(
            "\n".join(wp) + "\n", encoding="utf-8"
        )
        # iterations log: preCICE-local TimeWindow
        it = [
            "  TimeWindow  TotalIterations  Iterations  Convergence  QNColumns  DeletedQNColumns  DroppedQNColumns"
        ]
        total = 0
        for w in range(first, last + 1):
            n_it = round(signals["iterations"](w))
            total += n_it
            it.append(f"  {w - offset}  {total}  {n_it}  1  {round(signals['qn'](w))}  0  0")
        (solid / f"precice-Solid-iterations{tag}.log").write_text(
            "\n".join(it) + "\n", encoding="utf-8"
        )
        # Solid.log: preCICE markers (local numbering) + residual lines
        lines = []
        for w in range(first, last + 1):
            lines.append(
                f"---[precice] \x1b[0m it 1 (min: 1, max: 50), time-window {w - offset}, "
                f"t {(w - offset) * DT} (max: 0.16), Dt 2e-05, max-dt 2e-05\n"
            )
            lines.append(
                f" largest residual force= {signals['resid'](w):.6f} in node 2030 and dof 2\n"
            )
        (tutorial / f"Solid{tag}.log").write_text("".join(lines), encoding="utf-8")


def _pair(
    tmp_path: Path, treatment_signals: dict[str, Signal], *, split: bool = True
) -> tuple[Path, Path]:
    control = tmp_path / "control"
    treatment = tmp_path / "treatment"
    _write_run(control, _control_signals(), split_at=None)
    _write_run(treatment, treatment_signals, split_at=R if split else None)
    return control / "tutorial", treatment / "tutorial"


def _score(control_root: Path, treatment_root: Path, *, restarts: list[int]) -> dict[str, Any]:
    control = read_r3_inputs(control_root, dt=DT, restart_windows=[])
    treatment = read_r3_inputs(treatment_root, dt=DT, restart_windows=restarts)
    return score_r3(
        control,
        treatment,
        restart_window=R,
        requested_windows=N,
        early_windows=50,
        late_windows=50,
        refill_windows=10,
    )


def _with(base: dict[str, Signal], **overrides: Signal) -> dict[str, Signal]:
    out = dict(base)
    out.update(overrides)
    return out


# --- the pre-registration itself ----------------------------------------------------------


def test_the_bands_are_q1s_verbatim_and_the_windows_are_the_adrs() -> None:
    driver = _driver()
    assert R3_SPAN_MEAN_BAND == driver._Q1_SPAN_MEAN_BAND == 0.02
    assert R3_TRACE_BAND == driver._Q1_TRACE_BAND == 0.05
    assert (R3_EARLY_WINDOWS, R3_LATE_WINDOWS, R3_REFILL_WINDOWS) == (200, 200, 30)
    assert driver.R3_RESTART_WINDOW == 4000
    assert driver.R3_CONTROL_RUN_ID == "hg2007_flexible_foil-20260912-161321"


# --- the segment join ----------------------------------------------------------------------


def test_segments_join_on_global_windows_and_the_later_segment_wins(tmp_path: Path) -> None:
    control_root, treatment_root = _pair(tmp_path, _control_signals())
    control = read_r3_inputs(control_root, dt=DT, restart_windows=[])
    treatment = read_r3_inputs(treatment_root, dt=DT, restart_windows=[R])
    for name in ("forces", "power", "watchpoint", "iterations"):
        c, t = getattr(control, name), getattr(treatment, name)
        assert t.windows.tolist() == c.windows.tolist(), name
        for col in c.values:
            np.testing.assert_allclose(
                t.value(col), c.value(col), rtol=0, atol=0, err_msg=f"{name}.{col}"
            )
    assert treatment.residuals.is_contiguous
    assert (treatment.residuals.first_window, treatment.residuals.last_window) == (1, N)


def test_a_rotation_without_a_recorded_restart_is_refused(tmp_path: Path) -> None:
    _, treatment_root = _pair(tmp_path, _control_signals())
    with pytest.raises(R3Error, match="segment file"):
        segment_files(treatment_root, "Solid", "log", restart_windows=[])
    with pytest.raises(R3Error, match="segment file"):
        segment_files(treatment_root, "Solid", "log", restart_windows=[R, 2 * R])


# --- the four clauses ----------------------------------------------------------------------


def test_an_identical_treatment_is_transparent_on_all_four_clauses(tmp_path: Path) -> None:
    control_root, treatment_root = _pair(tmp_path, _control_signals())
    score = _score(control_root, treatment_root, restarts=[R])
    assert score["passed"] is True
    assert score["a"]["thrust"]["q1a_applicable"] is True
    assert score["a"]["lift"]["q1a_applicable"] is False  # |mean| / p2p ~ 0
    assert score["a"]["power"]["q1a_applicable"] is False
    assert score["b"]["identical_run_degenerate"] is True
    assert score["c"]["verdict"] == "eliminated"
    assert score["d"]["refilled_at_window"] == R + 1


def test_a_thrust_shift_beyond_two_percent_fails_q1a(tmp_path: Path) -> None:
    base = _control_signals()
    control_root, treatment_root = _pair(
        tmp_path, _with(base, fx=lambda w: base["fx"](w) * (1.03 if w > R else 1.0))
    )
    score = _score(control_root, treatment_root, restarts=[R])
    assert score["a"]["thrust"]["q1a_within_band"] is False
    assert score["a"]["passed"] is False and score["passed"] is False


def test_a_lift_trace_deviation_beyond_five_percent_of_peak_to_peak_fails_q1b(
    tmp_path: Path,
) -> None:
    base = _control_signals()
    control_root, treatment_root = _pair(
        tmp_path, _with(base, fy=lambda w: base["fy"](w) + (2.0e-3 if w > R else 0.0))
    )
    score = _score(control_root, treatment_root, restarts=[R])
    assert score["a"]["lift"]["q1a_within_band"] is None  # not applicable, never gates
    assert score["a"]["lift"]["q1b_within_band"] is False
    assert score["a"]["passed"] is False


def test_a_decaying_transient_passes_b_and_a_shift_fails_it(tmp_path: Path) -> None:
    base = _control_signals()
    control_root, treatment_root = _pair(
        tmp_path,
        _with(
            base,
            d1=lambda w: base["d1"](w) + (1.0e-6 * math.exp(-(w - R) / 20.0) if w > R else 0.0),
        ),
    )
    score = _score(control_root, treatment_root, restarts=[R])
    assert (
        score["b"]["passed"] is True
        and score["b"]["early_max_abs_delta"] > score["b"]["late_max_abs_delta"]
    )
    control_root, treatment_root = _pair(
        tmp_path / "shift", _with(base, d1=lambda w: base["d1"](w) + (1.0e-6 if w > R else 0.0))
    )
    score = _score(control_root, treatment_root, restarts=[R])
    assert score["b"]["passed"] is False


def test_a_divergent_treatment_fails_c(tmp_path: Path) -> None:
    base = _control_signals()
    # the period-2 signature: odd windows grow, even stay -- the parity prong fires
    control_root, treatment_root = _pair(
        tmp_path, _with(base, resid=lambda w: 5.0 * (1.03 ** (w - R)) if (w > R and w % 2) else 5.0)
    )
    score = _score(control_root, treatment_root, restarts=[R])
    assert score["c"]["verdict"] == "recurrence-detected"
    assert score["c"]["passed"] is False


def test_a_slow_history_refill_fails_d(tmp_path: Path) -> None:
    base = _control_signals()
    control_root, treatment_root = _pair(
        tmp_path, _with(base, qn=lambda w: min(50.0, 2.0 * (w - R)) if w > R else 50.0)
    )
    score = _score(control_root, treatment_root, restarts=[R])
    assert score["d"]["refilled_at_window"] == R + 25
    assert score["d"]["passed"] is False  # deadline R + 10 in this shrunken fixture
    control_root, treatment_root = _pair(
        tmp_path / "fast", _with(base, qn=lambda w: min(50.0, 10.0 * (w - R)) if w > R else 50.0)
    )
    score = _score(control_root, treatment_root, restarts=[R])
    assert score["d"]["refilled_at_window"] == R + 5 and score["d"]["passed"] is True


def test_a_treatment_that_did_not_complete_cannot_pass_c(tmp_path: Path) -> None:
    control_root, treatment_root = _pair(tmp_path, _control_signals())
    solid_log = treatment_root / "Solid.log"
    text = solid_log.read_text(encoding="utf-8")
    cut = text.index(f"time-window {N - R - 100},")
    solid_log.write_text(text[:cut], encoding="utf-8")
    control = read_r3_inputs(control_root, dt=DT, restart_windows=[])
    treatment = read_r3_inputs(treatment_root, dt=DT, restart_windows=[R])
    score = score_r3(
        control,
        treatment,
        restart_window=R,
        requested_windows=N,
        early_windows=50,
        late_windows=50,
        refill_windows=10,
    )
    assert score["c"]["completed"] is False and score["c"]["passed"] is False


def test_two_draw_context_reports_what_determinism_alone_does(tmp_path: Path) -> None:
    base = _control_signals()
    control_root, other_root = _pair(
        tmp_path, _with(base, d1=lambda w: base["d1"](w) + 1.0e-9 * w), split=False
    )
    control = read_r3_inputs(control_root, dt=DT, restart_windows=[])
    other = read_r3_inputs(other_root, dt=DT, restart_windows=[])
    ctx = two_draw_context(
        control, other, restart_window=R, requested_windows=N, early_windows=50, late_windows=50
    )
    assert (
        ctx["late_max_abs_delta"] > ctx["early_max_abs_delta"]
    )  # drift grows: context, not a clause


# --- the driver mode -------------------------------------------------------------------------


def _submission(
    path: Path, run_id: str, case_host: Path, *, restarts: list[int] | None = None
) -> Path:
    driver = _driver()
    record: dict[str, Any] = {
        "schema": driver.SUBMISSION_SCHEMA,
        "run_id": run_id,
        "session": f"fsi-{run_id}",
        "host": "aero-dev",
        "arm": "flexible",
        "rung": "mid",
        "case_host_path": str(case_host),
        "spec_knobs": {
            "arm": "flexible",
            "rung": "mid",
            "time_window_size": DT,
            "max_time": N * DT,
            "wall_clock_ceiling_s": 86400,
            "numerics_label": "adr040-candidate",
            "mpi_ranks": 4,
            "coupling_scheme": "parallel-implicit",
            "hht_alpha": -0.05,
            "solid_sif": "calculix-precice.sif",
        },
    }
    if restarts is not None:
        record["restart_windows"] = restarts
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_the_driver_refuses_the_wrong_control_and_a_different_shape(tmp_path: Path) -> None:
    driver = _driver()
    control_root, treatment_root = _pair(tmp_path, _control_signals())
    wrong = _submission(tmp_path / "c.json", "hg2007_flexible_foil-wrong", control_root.parent)
    treat = _submission(
        tmp_path / "t.json", "hg2007_flexible_foil-treat", treatment_root.parent, restarts=[R]
    )
    with pytest.raises(SystemExit, match="control is"):
        driver._score_r3(
            driver.argparse.Namespace(
                score_r3=[wrong, treat], r3_baseline=None, restart_window=R, out=None
            )
        )
    control = _submission(tmp_path / "c2.json", driver.R3_CONTROL_RUN_ID, control_root.parent)
    data = json.loads(treat.read_text(encoding="utf-8"))
    data["spec_knobs"]["hht_alpha"] = 0.0
    treat.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SystemExit, match="not the control's shape"):
        driver._score_r3(
            driver.argparse.Namespace(
                score_r3=[control, treat], r3_baseline=None, restart_window=R, out=None
            )
        )


def test_a_control_vs_control_reading_may_not_be_written_as_the_r3_record(tmp_path: Path) -> None:
    driver = _driver()
    control_root, _ = _pair(tmp_path, _control_signals())
    control = _submission(tmp_path / "c.json", driver.R3_CONTROL_RUN_ID, control_root.parent)
    out = _REPO_ROOT / "data" / "vv" / driver.R3_RECORD_NAME
    with pytest.raises(SystemExit, match="calibration"):
        driver._score_r3(
            driver.argparse.Namespace(
                score_r3=[control, control], r3_baseline=None, restart_window=R, out=out
            )
        )
    assert not out.exists()


# --- the real control, against itself (the scorer's calibration) ----------------------------

_CONTROL = Path("/mnt/aero-nfs/runs/hg2007_flexible_foil-20260912-161321")


@pytest.mark.skipif(not (_CONTROL / "tutorial").is_dir(), reason="the NFS share is not mounted")
def test_the_real_control_reads_as_transparent_against_itself_and_fixes_a10() -> None:
    control = read_r3_inputs(_CONTROL / "tutorial", dt=DT, restart_windows=[])
    score = score_r3(control, control, restart_window=4000, requested_windows=8000)
    assert score["passed"] is True, json.dumps({k: score[k]["passed"] for k in "abcd"})
    a = score["a"]
    # A10, from the control's own numbers over windows 4001-8000
    assert (
        a["thrust"]["q1a_applicable"] is True
        and a["thrust"]["control_mean_over_peak_to_peak"] > 1.0
    )
    assert (
        a["lift"]["q1a_applicable"] is False and a["lift"]["control_mean_over_peak_to_peak"] < 0.05
    )
    assert (
        a["power"]["q1a_applicable"] is False
        and a["power"]["control_mean_over_peak_to_peak"] < 0.05
    )
    assert score["b"]["identical_run_degenerate"] is True
    assert score["c"]["verdict"] == "eliminated" and score["c"]["windows_reached"] == 8000
    assert score["d"]["refilled_at_window"] is not None and score["d"]["refilled_at_window"] <= 4030
