"""Two readers of the same implicit-coupling artefact must not disagree.

Under ``parallel-implicit`` coupling preCICE re-does a time window until it converges: the
OpenFOAM adapter rewinds ``runTime``, the ``forces`` object re-executes, and ``force.dat``
gains one row per coupling ITERATION at each window time. Only the last is converged.

``ccx_dat`` already treated the CalculiX ``.dat`` that way, and the coded interface-power
object's own docstring states the rule -- but ``strictly_increasing_mask`` kept the FIRST
row. Left alone that would have built ``C_T`` and ``C_P1`` from unconverged iterates while
``P2`` and ``P3`` came from converged ones, and because the flexible arm needs more coupling
iterations than the rigid one, the bias would have DIFFERED BETWEEN ARMS and landed in the
gated increment.

Nothing downstream could have caught it, which is the point of this file: after
de-duplication both arms carry one row per window at identical times, so
``assert_common_time_base`` passes; D10 compares two quantities that are both taken from the
last iterate; and ``eta`` merely mixes the two silently. The tests below therefore drive the
disagreement itself rather than any of its consequences.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from aero.adapters.openfoam.flexible_foil import INTERFACE_POWER_TAG, read_interface_power
from aero.adapters.openfoam.force_io import (
    classify_repeat_cadence,
    last_occurrence_mask,
    read_force_history,
    strictly_increasing_mask,
)
from aero.adapters.precice.ccx_dat import read_reaction_forces

pytestmark = pytest.mark.stage_20


def _force_dat(path: Path, rows: list[tuple[float, float, float]]) -> Path:
    """A `forces` FO file in the parenthesised layout, one row per (t, fx, fy)."""
    lines = [
        "# Forces",
        "# CofR : (0 0 0)",
        "# Time forces(pressure viscous porous) moment(pressure viscous porous)",
    ]
    for t, fx, fy in rows:
        lines.append(f"{t!r}\t(({fx!r} {fy!r} 0) (0 0 0) (0 0 0))\t((0 0 0) (0 0 0) (0 0 0))")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


#: Three windows, taking 2, 3 and 1 coupling iterations. The LAST row of each window is
#: the converged one; the earlier rows are the accelerator's guesses and are visibly
#: different, so a reader that keeps the wrong one is caught by value, not by count.
_COUPLED_ROWS = [
    (0.001, 10.0, 1.0),  # window 1, iterate 1 (guess)
    (0.001, 11.0, 1.1),  # window 1, iterate 2 (converged)
    (0.002, 20.0, 2.0),  # window 2, iterate 1
    (0.002, 21.0, 2.1),  # window 2, iterate 2
    (0.002, 22.0, 2.2),  # window 2, iterate 3 (converged)
    (0.003, 30.0, 3.0),  # window 3, iterate 1 (converged)
]
_N_WINDOWS = 3
_TOTAL_ITERATIONS = 6


def test_the_two_masks_disagree_and_that_is_the_whole_defect() -> None:
    """A regression pin on the disagreement itself: first-vs-last, on one array."""
    t = np.asarray([r[0] for r in _COUPLED_ROWS], dtype=np.float64)
    first = np.flatnonzero(strictly_increasing_mask(t))
    last = np.flatnonzero(last_occurrence_mask(t))
    assert first.tolist() == [0, 2, 5]
    assert last.tolist() == [1, 4, 5]
    assert first.size == last.size == _N_WINDOWS


def test_the_coupled_policy_keeps_the_converged_iterate(tmp_path: Path) -> None:
    history = read_force_history(_force_dat(tmp_path / "force.dat", _COUPLED_ROWS), repeats="last")
    assert history.t.tolist() == [0.001, 0.002, 0.003]
    assert history.pressure[:, 0].tolist() == [11.0, 22.0, 30.0]
    assert history.n_dropped == len(_COUPLED_ROWS) - _N_WINDOWS


def test_the_default_policy_is_unchanged_so_earlier_records_do_not_move(tmp_path: Path) -> None:
    """Stage 10/11/13 read their force files with the first-row rule and their records
    stand on it. The coupled fix is a new policy, never a change of default."""
    path = _force_dat(tmp_path / "force.dat", _COUPLED_ROWS)
    assert read_force_history(path).pressure[:, 0].tolist() == [10.0, 20.0, 30.0]
    assert read_force_history(path, repeats="first").pressure[:, 0].tolist() == [10.0, 20.0, 30.0]


def test_raw_keeps_everything_so_the_repeats_can_be_classified_first(tmp_path: Path) -> None:
    raw = read_force_history(_force_dat(tmp_path / "force.dat", _COUPLED_ROWS), repeats="raw")
    assert raw.t.size == len(_COUPLED_ROWS)
    assert raw.n_dropped == 0
    cadence = classify_repeat_cadence(
        raw.t, n_windows=_N_WINDOWS, total_iterations=_TOTAL_ITERATIONS
    )
    assert cadence.kind == "per-iteration"
    assert cadence.n_distinct == _N_WINDOWS
    assert cadence.n_repeats == _TOTAL_ITERATIONS - _N_WINDOWS


def test_a_record_with_no_repeats_classifies_as_per_window() -> None:
    t = np.asarray([0.001, 0.002, 0.003], dtype=np.float64)
    cadence = classify_repeat_cadence(t, n_windows=3, total_iterations=3)
    assert cadence.kind == "per-window"
    assert cadence.n_repeats == 0


def test_an_unexplained_repeat_raises_rather_than_picking_a_branch() -> None:
    """The likely cause is a `timePrecision` too coarse for the window size, which deletes
    rows silently. Guessing which branch is closer would turn that into a plausible number.
    """
    t = np.asarray([0.001, 0.001, 0.002, 0.003], dtype=np.float64)
    with pytest.raises(ValueError, match="timePrecision"):
        classify_repeat_cadence(t, n_windows=3, total_iterations=7)


def test_the_force_reader_and_the_ccx_reader_now_agree(tmp_path: Path) -> None:
    """The headline property: given the same repeated-time structure, the fluid-side and
    solid-side readers keep the same row of each window. Before this commit one kept the
    first and the other the last, and the mismatch was invisible in every downstream check.
    """
    force = read_force_history(_force_dat(tmp_path / "force.dat", _COUPLED_ROWS), repeats="last")

    dat = tmp_path / "solid.dat"
    records = []
    for t, _, fy in _COUPLED_ROWS:
        records.append("")
        records.append(f" total force (fx,fy,fz) for set NNOSE and time  {t:.7E}")
        records.append("")
        records.append(f"       0.000000E+00  {fy:.6E}  0.000000E+00")
    dat.write_text("\n".join(records) + "\n", encoding="utf-8")
    reaction = read_reaction_forces(
        dat, iterations_per_window=np.asarray([2, 3, 1], dtype=np.int64)
    )

    assert reaction.cadence == "per-iteration"
    assert reaction.times.tolist() == pytest.approx(force.t.tolist())
    # Both took the LAST row at each repeated time: 1.1, 2.2, 3.0.
    assert reaction.forces[:, 1].tolist() == pytest.approx([1.1, 2.2, 3.0])
    assert force.viscous[:, 1].tolist() == pytest.approx([0.0, 0.0, 0.0])
    assert force.pressure[:, 1].tolist() == pytest.approx([1.1, 2.2, 3.0])


# --------------------------------------------------------------------------------------
# The interface-power reader
# --------------------------------------------------------------------------------------


def _log(rows: list[tuple[float, float, float, float]]) -> str:
    lines = ["Starting time loop", ""]
    for t, power, fx, fy in rows:
        lines.append(f"Time = {t}")
        lines.append(f"{INTERFACE_POWER_TAG} {t!r} {power!r} {fx!r} {fy!r}")
    lines.append("End")
    return "\n".join(lines) + "\n"


def test_the_interface_power_reader_defaults_to_the_converged_iterate() -> None:
    history = read_interface_power(
        _log(
            [
                (0.001, -5.0, 10.0, 1.0),
                (0.001, -5.5, 11.0, 1.1),
                (0.002, -9.0, 22.0, 2.2),
            ]
        )
    )
    assert history.t.tolist() == [0.001, 0.002]
    assert history.power.tolist() == [-5.5, -9.0]
    assert history.force[:, 0].tolist() == [11.0, 22.0]
    assert history.n_dropped == 1


def test_the_interface_power_reader_is_loud_when_the_object_never_ran() -> None:
    """A missing coded object is the difference between measuring P2 and inventing it.

    OpenFOAM refuses to compile a coded object as root, so this is the exact symptom of a
    participant that did not drop to `run_as_uid` -- and the run otherwise looks fine.
    """
    with pytest.raises(ValueError, match="did not run"):
        read_interface_power("Time = 0.001\nTime = 0.002\nEnd\n")


def test_the_summed_force_is_carried_so_it_can_be_checked_against_force_dat() -> None:
    """P2 is only trustworthy if it summed the same per-face force `force.dat` reports.

    Measured at twelve significant figures on the session-5 spike; the columns exist so the
    readout can assert it on every run rather than on the day it was measured.
    """
    history = read_interface_power(_log([(0.001, -5.5, 11.0, 1.1)]))
    assert history.force.shape == (1, 2)
    assert history.force[0].tolist() == [11.0, 1.1]
