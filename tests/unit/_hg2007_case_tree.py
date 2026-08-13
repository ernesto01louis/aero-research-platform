"""A complete, settled HG2007 coupled case tree — the only way to execute D10 before wave 1.

`read_arm` has never completed on a real coupled run, and it cannot: clearing `load()`
needs `analysis_discard_s + analysis_min_cycles * period` of physical time, which at the
campaign's own numbers is 13.19 s — about 660 000 coupling windows. Every probe that has
ever run is 500 windows, 0.01 s, and refuses at the discard guard. So the join,
`analyse_limit_cycle` on the joined base, `gated_means`, P1/P2/P3 and the D10 closure have
never executed together, and would first have done so at the end of wave 1.

This builds the case they need. It is a FIXTURE — bytes this repo wrote — and its job is
not to stand in for a solve. Its job is to execute a path that has never executed, and to
make its arithmetic checkable: the series are ANALYTIC, and chosen so that

    P3 == P2 exactly, by construction,

which makes the D10 closure a number the test can assert rather than merely a number the
code produced. `hg2007_readout`'s module header states the identity holds exactly under
ALPHA = 0 with no damping; this is that statement, executed.

Two things are borrowed rather than re-invented. The spec comes from
`tests/stage_20/_hg2007.py`, whose docstring explains why a second hand-maintained copy of
the fluid/solid agreement drifts. The settling shape — a transient anchored at the discard
boundary plus small noise, because the convergence detector refuses a noiseless record —
comes from `tests/stage_20/_settling.py`.

The time constants are SCALED, not the campaign's: a 0.05 s period and a 0.1 s discard put
eight settled cycles inside 500 windows. The plumbing under test does not know the
difference; the wall clock does.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from aero.adapters._base import CaseDir, ResultHandle
from aero.adapters.precice.case import CASE_ROOT_DIRNAME, CoupledCaseSpec
from aero.adapters.precice.solver import PreciceCoupledSolver
from aero.postprocess.flapping_kinematics import FlappingKinematics

from tests.stage_20._hg2007 import (
    authored_source,
    authored_spec,
    fluid,
    participants,
    section,
    solid,
)

DT = 1.0e-3
N_WINDOWS = 500
MAX_TIME = N_WINDOWS * DT  # 0.5 s
FREQUENCY = 20.0  # period 0.05 s, so 0.4 s past the discard is EIGHT cycles
PERIOD = 1.0 / FREQUENCY
DISCARD_S = 0.1
MIN_CYCLES = 4

_RNG = np.random.default_rng(20260813)

#: Coupling iterations per window. Varied so the record is genuinely per-ITERATION and the
#: cadence classifier has something to classify; >= 2 in window 1 because the coded function
#: object does not emit on its very first execution, so that window carries one row fewer.
_ITERATIONS = (3, 2, 4)


def _iterations() -> np.ndarray:
    return np.asarray([_ITERATIONS[k % len(_ITERATIONS)] for k in range(N_WINDOWS)], dtype=np.int64)


def _settling(t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`_settling.py`'s shape: a transient that starts decaying AT the discard boundary."""
    transient = 0.25 * np.exp(-np.maximum(t - DISCARD_S, 0.0) / (0.30 * PERIOD))
    noise = 0.004 * _RNG.standard_normal(t.size)
    return transient, noise


def _wave(
    t: np.ndarray, *, mean: float, amplitude: float, phase: float, harmonic: int = 1
) -> np.ndarray:
    transient, noise = _settling(t)
    return (
        mean
        + amplitude * np.sin(2.0 * np.pi * harmonic * t / PERIOD + phase)
        + transient * amplitude
        + noise * amplitude
    )


def _fortran_e(x: float) -> str:
    """CalculiX prints 7 significant digits in Fortran's 0.dddddddE+xx form."""
    if x == 0.0:
        return "0.0000000E+00"
    exponent = math.floor(math.log10(abs(x))) + 1
    return f"{x / 10.0**exponent:.7f}E{exponent:+03d}"


def _txt_table(path: Path, header: str, rows: list[str]) -> None:
    """preCICE's TXTTableWriter PREFIXES each row with a newline and never ends the last."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "".join("\n" + r for r in rows), encoding="utf-8")


def build(
    root: Path, *, discard_s: float = DISCARD_S, min_cycles: int = MIN_CYCLES
) -> tuple[PreciceCoupledSolver, ResultHandle, CoupledCaseSpec]:
    """Materialize the authored case under `root`, then write the outputs a run would leave.

    Returns what `--collect` holds at the moment it calls `read_arm`, so the test drives the
    same object graph the driver does rather than a re-assembly of it.

    ``discard_s`` is a parameter so a caller can build the SAME case with a discard longer
    than the record — which is the state every real probe is in, and the one that refuses.
    """
    sec = section()
    kinematics = FlappingKinematics(
        stroke_amplitude=0.0175,
        frequency=FREQUENCY,
        pitch_amplitude_deg=0.0,
        stroke_plane_deg=90.0,
    )
    spec = authored_spec(
        source=authored_source(
            fluid=fluid(sec, time_window_size=DT, max_time=MAX_TIME),
            solid=solid(sec, time_window_size=DT, max_time=MAX_TIME, kinematics=kinematics),
        ),
        # `run_as_uid=None` on the case AND on every participant, or the validator refuses
        # the mix. It makes `_write_case` skip its `_chown_tree`, which needs root and
        # therefore fails on an unprivileged CI runner (`Operation not permitted`) while
        # passing for anyone developing as root. Nothing here is ever EXECUTED — the uid
        # drop exists so participants can write into the case they were given — and the
        # materialized bytes are identical either way, so the readout under test cannot
        # tell the difference.
        participants=tuple(p.model_copy(update={"run_as_uid": None}) for p in participants()),
        run_as_uid=None,
        max_time=MAX_TIME,
        analysis_discard_s=discard_s,
        analysis_min_cycles=min_cycles,
    )
    solver = PreciceCoupledSolver()
    solver._write_case(spec, root)

    case_root = root / CASE_ROOT_DIRNAME
    case = case_root / spec.case_subdir
    source = spec.source
    fluid_dir = case / source.fluid_participant_dir
    solid_dir = case / source.solid_participant_dir

    iterations = _iterations()
    windows = np.arange(1, N_WINDOWS + 1, dtype=np.int64)
    window_t = windows.astype(np.float64) * DT  # the window-END instants

    # --- the SOLID's watch-points: the D0 pitch, and the plunge it was driven through -----
    # theta is set through the geometry `load()` reads it back out of, so the pitch trace is
    # controlled exactly rather than hoped for.
    watch_t = np.arange(0, N_WINDOWS + 1, dtype=np.float64) * DT
    theta_deg = _wave(watch_t, mean=0.0, amplitude=5.0, phase=0.0)
    chordwise0 = source.solid.chord - source.solid.surface_x[0]
    tip_uy = chordwise0 * np.tan(np.radians(theta_deg))
    # The nose is DRIVEN through the prescribed plunge, and `load()` checks the amplitude it
    # reads back against the kinematics spec — a disagreement there is a perfectly
    # convergent run of a different experiment.
    nose_uy = np.asarray(kinematics.evaluate(watch_t)["y"], dtype=np.float64)

    header = "  Time  Coordinate0  Coordinate1  Displacement0  Displacement1  Force0  Force1"
    for name, uy in (("Nose", nose_uy), ("Trailing-Edge", tip_uy)):
        rows = [
            f" {t:.8e}   4.75956328e-06   0.00000000e+00   0.00000000e+00   {v:.8e}"
            f"   0.00000000e+00   0.00000000e+00"
            for t, v in zip(watch_t, uy, strict=True)
        ]
        _txt_table(solid_dir / f"precice-Solid-watchpoint-{name}.log", header, rows)

    # --- the per-window physics ----------------------------------------------------------
    vy = np.asarray(kinematics.evaluate(window_t)["vy"], dtype=np.float64)
    # Thrust is at TWICE the plunge frequency; the fundamental is the pitch, which is why
    # `read_arm` segments on D0 and not on C_T.
    fx = _wave(window_t, mean=-2.0e-3, amplitude=5.0e-4, phase=0.7, harmonic=2)
    fy = _wave(window_t, mean=0.0, amplitude=4.0e-3, phase=1.1)
    # The reaction is proportional to the plunge velocity, so the interface power it implies
    # has a positive cycle mean rather than averaging to zero across the stroke.
    reaction_fy = 1.0e-3 * vy * (1.0 + _settling(window_t)[0] + _settling(window_t)[1])
    # THE identity: the fluid's interface power IS the solid's reaction power. Written from
    # the same floats `read_arm` will multiply, so D10 closes to rounding and not to luck.
    power = reaction_fy * vy

    # --- the FLUID's records: per-iteration, stamped at the window START ------------------
    # Structure measured on both surviving I4 arms (§6.38): sum(iterations) rows over
    # n_windows + 1 distinct times, window 1 one row short, one trailing row at max_time.
    force_lines = [
        "# Force             ",
        "# CofR              : (0.000000000000e+00 0.000000000000e+00 0.000000000000e+00)",
        "#",
        "# Time              \ttotal_x total_y total_z\tpressure_x pressure_y pressure_z"
        "\tviscous_x viscous_y viscous_z",
    ]
    power_lines: list[str] = []

    def _emit(stamp: float, x: float, y: float, p: float, repeats: int) -> None:
        for _ in range(repeats):
            force_lines.append(
                f"{stamp!r}                    {x:.12e} {y:.12e} 0.000000000000e+00 "
                f"{x:.12e} {y:.12e} 0.000000000000e+00 "
                f"0.000000000000e+00 0.000000000000e+00 0.000000000000e+00"
            )
            power_lines.append(f"aeroInterfacePower {stamp!r} {p!r} {x!r} {y!r}")

    for k in range(N_WINDOWS):
        stamp = float(k) * DT  # window k+1 is stamped at its START
        repeats = int(iterations[k]) - (1 if k == 0 else 0)
        _emit(stamp, float(fx[k]), float(fy[k]), float(power[k]), repeats)
    _emit(float(N_WINDOWS) * DT, float(fx[-1]), float(fy[-1]), float(power[-1]), 1)

    forces_path = fluid_dir / "postProcessing/forces1/0/force.dat"
    forces_path.parent.mkdir(parents=True, exist_ok=True)
    forces_path.write_text("\n".join(force_lines) + "\n", encoding="utf-8")
    (case_root / "Fluid.log").write_text(
        "Create mesh for time = 0\n\n" + "\n".join(power_lines) + "\n", encoding="utf-8"
    )

    # --- the SOLID's reaction record: one row per window, stamped at the window END -------
    dat = []
    for k in range(N_WINDOWS):
        dat.append("")
        dat.append(f" total force (fx,fy,fz) for set NNOSE and time  {_fortran_e(window_t[k])}")
        dat.append("")
        dat.append(f"       {fx[k]:.6E} {reaction_fy[k]:.6E} 0.000000E+00")
    (solid_dir / f"{source.solid.name}.dat").write_text("\n".join(dat) + "\n", encoding="utf-8")

    # --- the coupling's own account, and the supervisor's verdict -------------------------
    iterations_header = "  TimeWindow  TotalIterations  Iterations  Convergence"
    running = 0
    iteration_rows = []
    for k in range(N_WINDOWS):
        running += int(iterations[k])
        iteration_rows.append(f"     {k + 1}      {running}      {int(iterations[k])}       1")
    _txt_table(fluid_dir / "precice-Fluid-iterations.log", iterations_header, iteration_rows)
    _txt_table(solid_dir / "precice-Solid-iterations.log", iterations_header, iteration_rows)

    (case_root / "coupled-status.json").write_text(
        json.dumps(
            {
                "run_id": "hg2007-synthetic",
                "stopped_by": "all-exited",
                "started_epoch": 1786571946,
                "ended_epoch": 1786574526,
                "wall_clock_s": 2580,
                "participants": [
                    {
                        "name": name,
                        "returncode": 0,
                        "started_epoch": 1786571946,
                        "ended_epoch": 1786574526,
                        "log_path": str(case_root / f"{name}.log"),
                    }
                    for name in ("Fluid", "Solid")
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (case_root / "Solid.log").write_text("CalculiX Version 2.20\n", encoding="utf-8")

    case_dir = CaseDir(
        run_id="hg2007-synthetic", spec=spec, host_path=root, remote_path=Path("/remote")
    )
    return solver, solver.reattach(case_dir, executor_returncode=0), spec
