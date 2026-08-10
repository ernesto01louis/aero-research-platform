"""The Courant reader against REAL bytes and against the repeat/window traps it exists for."""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.solver_log import SolverLogError, read_courant_history

pytestmark = pytest.mark.stage_20

_REAL_LOG = Path(__file__).resolve().parent / "fixtures/stage19_load_path/tutorial/Fluid.log"


def test_the_real_stage19_fluid_log_reads(tmp_path: Path) -> None:
    """A reader tested only against bytes its own test writes proves self-consistency."""
    if not _REAL_LOG.exists():
        pytest.skip("stage19 fixture log not present")
    history = read_courant_history(_REAL_LOG)
    # The fixture is a captured tail carrying exactly one Courant line; its value is
    # part of the committed record, so pin it rather than a vague bound.
    assert history.n_lines >= 1
    assert max(history.max) == 0.318


def test_repeated_iterations_keep_their_time_and_the_max_is_repeat_insensitive(
    tmp_path: Path,
) -> None:
    log = tmp_path / "Fluid.log"
    log.write_text(
        "Courant Number mean: 0.01 max: 0.05\n"
        "Time = 0.001\n"
        "Courant Number mean: 0.02 max: 0.30\n"
        "Time = 0.001\n"  # the adapter rewound: same window, second iteration
        "Courant Number mean: 0.02 max: 0.31\n"
        "Time = 0.002\n"
        "Courant Number mean: 0.03 max: 0.62\n",
        encoding="utf-8",
    )
    history = read_courant_history(log)
    assert history.t == (0.0, 0.001, 0.001, 0.002)
    assert history.max_over(t_start=0.0015) == 0.62
    assert history.max_over(t_start=0.0) == 0.62


def test_a_window_past_the_record_is_refused_not_zero(tmp_path: Path) -> None:
    log = tmp_path / "Fluid.log"
    log.write_text("Time = 0.001\nCourant Number mean: 0.02 max: 0.30\n", encoding="utf-8")
    with pytest.raises(SolverLogError, match="post-ramp"):
        read_courant_history(log).max_over(t_start=0.5)


def test_a_log_with_no_courant_lines_is_refused(tmp_path: Path) -> None:
    log = tmp_path / "Fluid.log"
    log.write_text("Time = 0.001\nExecutionTime = 1 s\n", encoding="utf-8")
    with pytest.raises(SolverLogError, match="no 'Courant Number"):
        read_courant_history(log)
