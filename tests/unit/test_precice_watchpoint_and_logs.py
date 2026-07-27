"""Unit tests for the preCICE watch-point reader and the coupling-convergence gate.

The formats here were read off preCICE v3.4.1's ``TXTTableWriter``, and two of its
properties are load-bearing: the header line is emitted with a leading two-space
delimiter and no comment marker, and data rows are newline-*prefixed*, so a file being
appended to has an unterminated — and possibly partial — final row.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.precice._txt_table import TxtTableError, read_txt_table
from aero.adapters.precice.logs import (
    CouplingConvergenceError,
    assert_coupling_converged,
    find_iterations_logs,
    read_iterations_log,
)
from aero.adapters.precice.watchpoint import WatchpointError, read_watchpoint

pytestmark = pytest.mark.stage_19

_WATCH_COLUMNS = (
    "Time",
    "Coordinate0",
    "Coordinate1",
    "Displacement0",
    "Displacement1",
    "Stress0",
    "Stress1",
)

_HEADER = "  Time  Coordinate0  Coordinate1  Displacement0  Displacement1  Stress0  Stress1"


def _watch_rows(n: int, *, t0: float = 0.001, dt: float = 0.001) -> list[str]:
    rows = []
    for i in range(n):
        t = t0 + i * dt
        rows.append(
            f"{t:.16f}  6.0000000000000000e-01  2.0000000000000000e-01  "
            f"{-1e-4 * i:.16e}  {1e-3 * i:.16e}  0.0000000000000000e+00  0.0000000000000000e+00"
        )
    return rows


def _write_watchpoint(path: Path, rows: list[str], *, trailing_newline: bool = False) -> Path:
    # preCICE prefixes each row with "\n" and never terminates the last one.
    text = _HEADER + "".join("\n" + row for row in rows) + ("\n" if trailing_newline else "")
    path.write_text(text, encoding="utf-8")
    return path


def test_reads_a_live_watchpoint(tmp_path: Path) -> None:
    path = _write_watchpoint(tmp_path / "precice-Solid-watchpoint-Flap-Tip.log", _watch_rows(5))
    trace = read_watchpoint(
        path, participant="Solid", watch_point="Flap-Tip", expected_columns=_WATCH_COLUMNS
    )
    assert trace.n_rows == 5
    assert trace.n_dropped == 0
    assert trace.columns == _WATCH_COLUMNS
    assert trace.signal("Displacement1").name == "Displacement1"


def test_a_partial_trailing_row_is_dropped_and_counted(tmp_path: Path) -> None:
    """Expected while the solve is running — must not be an error, must not be silent."""
    rows = _watch_rows(5)
    rows.append("0.0060000000000000  6.0000000000000000e-01  2.00000")  # mid-write
    path = _write_watchpoint(tmp_path / "wp.log", rows)
    trace = read_watchpoint(
        path, participant="Solid", watch_point="Flap-Tip", expected_columns=_WATCH_COLUMNS
    )
    assert trace.n_rows == 5
    assert trace.n_dropped == 1


def test_a_short_row_in_the_middle_is_corruption(tmp_path: Path) -> None:
    rows = _watch_rows(5)
    rows[2] = "0.003  6.0e-01"
    path = _write_watchpoint(tmp_path / "wp.log", rows)
    with pytest.raises(WatchpointError, match="corruption"):
        read_watchpoint(path, participant="Solid", watch_point="Flap-Tip")


def test_header_mismatch_refuses_positional_indexing(tmp_path: Path) -> None:
    """If upstream reorders `use-data`, the columns move. Guessing would transpose signals."""
    swapped = "  Time  Coordinate0  Coordinate1  Stress0  Stress1  Displacement0  Displacement1"
    path = tmp_path / "wp.log"
    path.write_text(swapped + "\n" + "\n".join(_watch_rows(3)), encoding="utf-8")
    with pytest.raises(WatchpointError, match="does not match the header predicted"):
        read_watchpoint(
            path, participant="Solid", watch_point="Flap-Tip", expected_columns=_WATCH_COLUMNS
        )


def test_header_only_is_loud(tmp_path: Path) -> None:
    path = _write_watchpoint(tmp_path / "wp.log", [])
    with pytest.raises(WatchpointError, match="no completed time windows"):
        read_watchpoint(path, participant="Solid", watch_point="Flap-Tip")


def test_non_monotonic_time_is_loud(tmp_path: Path) -> None:
    """A restarted run appended to an existing log would silently interleave two solves."""
    rows = _watch_rows(5)
    rows.append(rows[1])
    path = _write_watchpoint(tmp_path / "wp.log", rows)
    with pytest.raises(ValueError, match="strictly increasing"):
        read_watchpoint(path, participant="Solid", watch_point="Flap-Tip")


def test_truncate_keeps_the_early_window(tmp_path: Path) -> None:
    path = _write_watchpoint(tmp_path / "wp.log", _watch_rows(10))
    trace = read_watchpoint(path, participant="Solid", watch_point="Flap-Tip")
    cut = trace.truncate(t_max=0.005)
    assert cut.n_rows == 5
    assert cut.t[-1] <= 0.005


def test_missing_file_is_loud(tmp_path: Path) -> None:
    with pytest.raises(TxtTableError, match="no such file"):
        read_txt_table(tmp_path / "absent.log")


# --- coupling convergence -----------------------------------------------------------

_ITER_HEADER = "  TimeWindow  TotalIterations  Iterations  Convergence"


def _write_iterations(path: Path, rows: list[tuple[int, int, int, int]]) -> Path:
    body = "".join(f"\n{w:6d}  {t:6d}  {i:6d}  {c:6d}" for w, t, i, c in rows)
    path.write_text(_ITER_HEADER + body, encoding="utf-8")
    return path


def test_reads_iterations_log(tmp_path: Path) -> None:
    path = _write_iterations(
        tmp_path / "precice-Fluid-iterations.log",
        [(0, 12, 12, 1), (1, 20, 8, 1), (2, 26, 6, 1)],
    )
    report = read_iterations_log(path, participant="Fluid", max_iterations_configured=100)
    assert report.n_windows == 3
    assert report.all_converged
    assert report.max_observed_iterations == 12
    assert report.mean_iterations == pytest.approx(26 / 3)
    assert_coupling_converged(report)


def test_a_flagged_nonconverged_window_fails(tmp_path: Path) -> None:
    path = _write_iterations(tmp_path / "it.log", [(0, 5, 5, 1), (1, 15, 10, 0)])
    report = read_iterations_log(path, participant="Fluid", max_iterations_configured=100)
    assert report.n_nonconverged == 1
    with pytest.raises(CouplingConvergenceError, match="did not converge"):
        assert_coupling_converged(report)


def test_hitting_the_iteration_cap_counts_as_not_converged(tmp_path: Path) -> None:
    """preCICE proceeds after exhausting max-iterations; the numbers keep coming.

    Nothing downstream would notice, which is exactly why this is checked.
    """
    path = _write_iterations(tmp_path / "it.log", [(0, 5, 5, 1), (1, 105, 100, 1)])
    report = read_iterations_log(path, participant="Fluid", max_iterations_configured=100)
    assert report.n_nonconverged == 1
    with pytest.raises(CouplingConvergenceError, match="hit the cap"):
        assert_coupling_converged(report)


def test_more_iterations_than_configured_means_mismatched_inputs(tmp_path: Path) -> None:
    path = _write_iterations(tmp_path / "it.log", [(0, 200, 200, 1)])
    with pytest.raises(ValueError, match="configuration disagree"):
        read_iterations_log(path, participant="Fluid", max_iterations_configured=100)


def test_the_gate_applies_to_the_analysis_window(tmp_path: Path) -> None:
    """The start-up transient legitimately needs many iterations; the limit cycle must not."""
    path = _write_iterations(
        tmp_path / "it.log",
        [(0, 100, 100, 1), (1, 108, 8, 1), (2, 114, 6, 1), (3, 119, 5, 1)],
    )
    report = read_iterations_log(path, participant="Fluid", max_iterations_configured=100)
    with pytest.raises(CouplingConvergenceError):
        assert_coupling_converged(report)
    assert_coupling_converged(report.within(first_window=1, last_window=3))


def test_empty_iterations_log_is_loud(tmp_path: Path) -> None:
    path = tmp_path / "it.log"
    path.write_text(_ITER_HEADER, encoding="utf-8")
    with pytest.raises(CouplingConvergenceError, match="no time windows"):
        read_iterations_log(path, participant="Fluid", max_iterations_configured=100)


def test_no_iterations_log_anywhere_is_loud(tmp_path: Path) -> None:
    with pytest.raises(CouplingConvergenceError, match="never connected"):
        find_iterations_logs(tmp_path)


def test_find_iterations_logs_keys_by_participant(tmp_path: Path) -> None:
    (tmp_path / "fluid-openfoam").mkdir()
    (tmp_path / "solid-nutils").mkdir()
    _write_iterations(tmp_path / "fluid-openfoam" / "precice-Fluid-iterations.log", [(0, 1, 1, 1)])
    _write_iterations(tmp_path / "solid-nutils" / "precice-Solid-iterations.log", [(0, 1, 1, 1)])
    assert sorted(find_iterations_logs(tmp_path)) == ["Fluid", "Solid"]


# --- blockMesh cell-count parsing ---------------------------------------------------

# Captured verbatim from OpenFOAM-ESI v2412 running the pinned Turek-Hron blockMeshDict
# inside precice-fsi.sif. Pinned as a fixture because the field it feeds
# (MeshHandle.n_elements) is provenance-bearing: it is what identifies the mesh rung.
_REAL_BLOCKMESH_TAIL = """No patch pairs to merge

Writing polyMesh with 0 cellZones
----------------
Mesh Information
----------------
  boundingBox: (0 0 -0.1) (2.5 0.41 0.1)
  nPoints: 42938
  nCells: 20969
  nFaces: 84376
  nInternalFaces: 41438
----------------
Patches
----------------
  patch 0 (start: 41438 size: 20969) name: front
  patch 6 (start: 84042 size: 201) name: flap

End
"""


def test_blockmesh_cell_count_regex_matches_real_v2412_output() -> None:
    """blockMesh says "nCells:"; "cells:" is checkMesh's wording.

    Getting this wrong does not fail loudly by itself — the solver refuses to publish an
    unparseable count — but it stops every campaign at the mesh step, and the near-miss
    is the same class as Stage 18's pre-snap cell count reaching a provenance field.
    """
    from aero.adapters.precice.solver import _N_CELLS_RE

    match = _N_CELLS_RE.search(_REAL_BLOCKMESH_TAIL)
    assert match is not None
    assert int(match.group(1)) == 20969


def test_blockmesh_regex_does_not_match_patch_sizes() -> None:
    """`patch 0 (start: 41438 size: 20969)` must not be mistaken for a cell count."""
    from aero.adapters.precice.solver import _N_CELLS_RE

    assert len(_N_CELLS_RE.findall(_REAL_BLOCKMESH_TAIL)) == 1


def test_the_quasi_newton_participant_writes_extra_columns(tmp_path: Path) -> None:
    """Header captured verbatim from a real 200-window FSI3 calibration.

    The participant that runs the IQN-ILS acceleration appends three columns its peer
    does not. Demanding an exact 4-column header made a completed, fully-converged
    calibration unreadable — and those extra columns are the filter behaviour gate K3
    records as a diagnostic, so they are worth keeping rather than merely tolerating.
    """
    header = (
        "  TimeWindow  TotalIterations  Iterations  Convergence  "
        "QNColumns  DeletedQNColumns  DroppedQNColumns"
    )
    body = (
        "\n   199     701       3       1      24       0       1"
        "\n   200     705       4       1      25       1       1"
    )
    path = tmp_path / "precice-Solid-iterations.log"
    path.write_text(header + body, encoding="utf-8")

    report = read_iterations_log(path, participant="Solid", max_iterations_configured=100)
    assert report.n_windows == 2
    assert report.all_converged
    assert report.quasi_newton_columns == (
        "QNColumns",
        "DeletedQNColumns",
        "DroppedQNColumns",
    )


def test_a_reordered_iterations_header_is_still_loud(tmp_path: Path) -> None:
    """Accepting extra TRAILING columns must not weaken the leading-column contract."""
    path = tmp_path / "it.log"
    path.write_text(
        "  TimeWindow  Iterations  TotalIterations  Convergence\n     1       5       5       1",
        encoding="utf-8",
    )
    with pytest.raises(CouplingConvergenceError, match="does not begin with"):
        read_iterations_log(path, participant="Solid", max_iterations_configured=100)
