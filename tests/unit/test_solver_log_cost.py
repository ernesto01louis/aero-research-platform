"""The fluid cost reader — against the attribution traps, and against real campaign bytes.

This reader is the instrument ADR-040 argues from: it is what turns "the cost split is
hypothesis-ranked, not measured" (handoff §6.29) into a number. An attribution bug here
does not crash, it produces a plausible split — the failure class this stage keeps
finding — so every trap gets its own test.

In ``tests/unit`` rather than ``tests/stage_20`` because ``tests/stage_20`` is not in CI
(handoff §6.24) and the ADR-040 evidence chain must be enforced, not merely green.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.solver_log import (
    SolverLogError,
    read_fluid_cost_history,
)

pytestmark = pytest.mark.stage_20

#: The flexible arm's I4 calibration log — 500 coupling windows at dt 2e-5, the run
#: behind ``data/vv/stage20_i4_calibration.json``. Not committed (11.7 MB); the test
#: skips when the NFS mount is absent, exactly as the Stage-19 Courant test does.
_CAMPAIGN_LOG = Path("/mnt/aero-nfs/runs/hg2007_flexible_foil-20260810-144742/tutorial/Fluid.log")


def _step(time: str, solves: str, cpu: str, wall: str) -> str:
    return f"Time = {time}\n\n{solves}ExecutionTime = {cpu} s  ClockTime = {wall} s\n\n"


_SOLVE_P = (
    "GAMG:  Solving for p, Initial residual = 0.047, Final residual = 0.00044, No Iterations 72\n"
)
_SOLVE_P_FINAL = (
    "GAMG:  Solving for p, Initial residual = 0.0088, Final residual = 9.9e-08, No Iterations 271\n"
)
_SOLVE_UX = (
    "smoothSolver:  Solving for Ux, Initial residual = 0.0006, Final residual = 2.1e-09, "
    "No Iterations 1\n"
)
_SOLVE_DISP = (
    "DICPCG:  Solving for cellDisplacementx, Initial residual = 0.037, "
    "Final residual = 1.1e-18, No Iterations 3\n"
)


def test_solve_lines_attach_to_the_step_they_were_printed_in(tmp_path: Path) -> None:
    """Under implicit coupling the same ``Time =`` repeats; steps are still distinct.

    An ExecutionTime line CLOSES a step. A reader that grouped by distinct ``t`` would
    fold five coupling iterations into one step and report five times the per-step cost.
    """
    log = tmp_path / "Fluid.log"
    log.write_text(
        _step("0.0002", _SOLVE_P, "10.0", "10")
        # the adapter rewound: same physical time, second coupling iteration
        + _step("0.0002", _SOLVE_P + _SOLVE_P_FINAL, "13.0", "13")
        + _step("0.0004", _SOLVE_P, "15.0", "16"),
        encoding="utf-8",
    )
    history = read_fluid_cost_history(log)

    assert history.n_steps == 3
    assert [s.t for s in history.steps] == [0.0002, 0.0002, 0.0004]
    assert [s.iterations_by_field["p"] for s in history.steps] == [72, 343, 72]
    assert [s.solves_by_field["p"] for s in history.steps] == [1, 2, 1]


def test_the_cpu_delta_is_per_step_and_the_first_is_measured_from_zero(
    tmp_path: Path,
) -> None:
    """ExecutionTime is CUMULATIVE; the cost of a step is the difference."""
    log = tmp_path / "Fluid.log"
    log.write_text(
        _step("0.0002", _SOLVE_P, "10.0", "12")
        + _step("0.0004", _SOLVE_P, "13.5", "16")
        + _step("0.0006", _SOLVE_P, "16.0", "19"),
        encoding="utf-8",
    )
    history = read_fluid_cost_history(log)

    assert [s.d_execution_s for s in history.steps] == [10.0, 3.5, 2.5]
    assert [s.d_clock_s for s in history.steps] == [12.0, 4.0, 3.0]
    assert history.total_execution_s == 16.0
    assert history.total_clock_s == 19.0
    assert history.cpu_fraction_of_wall == pytest.approx(16.0 / 19.0)


def test_a_backwards_execution_time_is_refused(tmp_path: Path) -> None:
    """Two runs appended to one log would give one hugely negative per-step delta.

    Silently averaged in, that delta drags the mean rate down and every share computed
    from it is wrong — a plausible number from a file we do not understand.
    """
    log = tmp_path / "Fluid.log"
    log.write_text(
        _step("0.0002", _SOLVE_P, "10.0", "12")
        + _step("0.0004", _SOLVE_P, "13.5", "16")
        + _step("0.0002", _SOLVE_P, "2.0", "3"),  # a second run, appended
        encoding="utf-8",
    )
    with pytest.raises(SolverLogError, match="went backwards"):
        read_fluid_cost_history(log)


def test_iterations_sum_but_solves_count_within_one_step(tmp_path: Path) -> None:
    """8 solves of 100 iterations and 1 of 800 cost alike and mean different things.

    The iteration total is the cost regressor; the solve count is what says whether the
    expense is the discretisation's corrector structure or the linear solver's
    convergence rate. Collapsing them would hide which lever applies.
    """
    log = tmp_path / "Fluid.log"
    log.write_text(
        _step("0.0002", _SOLVE_P * 3 + _SOLVE_P_FINAL + _SOLVE_UX, "10.0", "10"),
        encoding="utf-8",
    )
    (step,) = read_fluid_cost_history(log).steps

    assert step.iterations_by_field == {"Ux": 1, "p": 72 * 3 + 271}
    assert step.solves_by_field == {"Ux": 1, "p": 4}


def test_the_solver_name_is_kept_per_field(tmp_path: Path) -> None:
    """A stack change must be visible IN the record, not inferred from the ADR beside it."""
    log = tmp_path / "Fluid.log"
    log.write_text(
        _step("0.0002", _SOLVE_P + _SOLVE_UX + _SOLVE_DISP, "10.0", "10"),
        encoding="utf-8",
    )
    (step,) = read_fluid_cost_history(log).steps

    assert step.solver_by_field == {
        "Ux": "smoothSolver",
        "cellDisplacementx": "DICPCG",
        "p": "GAMG",
    }


def test_iterations_per_step_groups_fields_for_the_regressor(tmp_path: Path) -> None:
    """``p`` and ``pcorr`` are one pressure-solve regressor; the reader must fold them."""
    pcorr = (
        "GAMG:  Solving for pcorr, Initial residual = 1, Final residual = 0.018, No Iterations 59\n"
    )
    log = tmp_path / "Fluid.log"
    log.write_text(
        _step("0.0002", pcorr + _SOLVE_P, "10.0", "10") + _step("0.0004", _SOLVE_P, "12.0", "12"),
        encoding="utf-8",
    )
    history = read_fluid_cost_history(log)

    assert list(history.iterations_per_step("p", "pcorr")) == [131.0, 72.0]
    assert list(history.iterations_per_step("p")) == [72.0, 72.0]
    # A field never solved contributes zero rather than raising: the vocabulary is the
    # log's, and a stack that drops pcorr is a legitimate ADR-040 candidate.
    assert list(history.iterations_per_step("nowhere")) == [0.0, 0.0]
    assert history.fields() == ("p", "pcorr")


def test_a_log_with_courant_lines_but_no_execution_time_is_refused(tmp_path: Path) -> None:
    """Named reason, mirroring ``read_courant_history``'s own refusal."""
    log = tmp_path / "Fluid.log"
    log.write_text("Time = 0.0002\nCourant Number mean: 0.01 max: 0.05\n", encoding="utf-8")
    with pytest.raises(SolverLogError, match="no 'ExecutionTime"):
        read_fluid_cost_history(log)


def test_the_real_campaign_log_reads_and_reproduces_the_i4_record() -> None:
    """A reader tested only against bytes its own test writes proves self-consistency.

    These numbers are the ADR-040 evidence: 500 windows x 5.254 mean coupling iterations
    = 2627 fluid step-solves, and 7988.69 s of CPU inside 8035 s of wall — so 99.4 % of
    the wave was the fluid participant computing, and every lever that attacks I/O,
    exchange or the solid is bounded by the remaining 0.6 %.
    """
    if not _CAMPAIGN_LOG.exists():
        pytest.skip("the I4 campaign log is on NFS and this box cannot see it")
    history = read_fluid_cost_history(_CAMPAIGN_LOG)

    assert history.n_steps == 2627
    assert history.total_execution_s == 7988.69
    assert history.total_clock_s == 8035.0
    assert history.cpu_fraction_of_wall == pytest.approx(0.9942, abs=5e-5)
    assert history.mean_seconds_per_step == pytest.approx(3.041, abs=5e-4)

    gamg = history.iterations_per_step("p", "pcorr")
    assert gamg.mean() == pytest.approx(960.5, abs=1.0)
    # 8 pressure solves per fluid step: nOuterCorrectors 2 x nCorrectors 2 x
    # (nNonOrthogonalCorrectors 1 + 1). This is what makes the corrector counts a lever.
    assert {s.solves_by_field["p"] for s in history.steps} == {8}
    assert history.steps[0].solver_by_field["p"] == "GAMG"
