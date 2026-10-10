"""The window join, and the measurement it rests on — against the real I4 bytes.

`--collect` -> `read_arm` had never been run on a real coupled run, and would have RAISED
on both surviving I4 arms after wave 1's weeks of wall clock. Two symptoms, one cause: the
fluid function objects stamp the coupling window START and CalculiX stamps the window END,
so `_assert_one_schedule` failed on shape (501 instants against 500) and
`classify_repeat_cadence` failed because a window-start record carries one distinct time
more than its arithmetic allowed.

The pure unit tests below pin the join. The `TestAgainstTheSurvivingI4Bytes` class pins the
MEASUREMENT the join rests on, against
``/mnt/aero-nfs/runs/hg2007_{flexible,rigid}_foil-20260810-1447*`` — the same bytes the
session-9 finding was made on and the same bytes the N4/N5 record cites. They skip when the
NFS mount is absent, because a CI runner without it is not evidence of anything; when it is
present, a regression here is a hard failure on real data rather than on a fixture written
to agree with the code.

In `tests/unit/` because `tests/stage_20` is not in CI (handoff §6.24).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from aero.adapters.openfoam.force_io import classify_repeat_cadence, read_force_history
from aero.adapters.precice.ccx_dat import read_reaction_forces
from aero.adapters.precice.logs import find_iterations_logs, read_iterations_log
from aero.adapters.precice.schedule import (
    ScheduleError,
    common_windows,
    select_windows,
    window_indices,
)

pytestmark = pytest.mark.stage_20

_DT = 2.0e-5
_RUNS = {
    "flexible": Path("/mnt/aero-nfs/runs/hg2007_flexible_foil-20260810-144742"),
    "rigid": Path("/mnt/aero-nfs/runs/hg2007_rigid_foil-20260810-144747"),
}

#: The Q1 equivalence runs: the same 500-window shape, produced by a 4-rank DECOMPOSED
#: fluid participant on the ADR-040 candidate stack. Wave 1 will be decomposed, and until
#: these were added every claim below rested on serial bytes alone.
_Q1_RUNS = {
    "flexible": Path("/mnt/aero-nfs/runs/hg2007_flexible_foil-20260812-215900"),
    "rigid": Path("/mnt/aero-nfs/runs/hg2007_rigid_foil-20260812-215908"),
}

#: One id space, so a claim added below is re-derived on BOTH decompositions rather than
#: on whichever set the author happened to be looking at.
_ALL_RUNS = {f"i4-{k}": v for k, v in _RUNS.items()} | {f"q1-{k}": v for k, v in _Q1_RUNS.items()}


def _idx(t: np.ndarray, stamp: str) -> np.ndarray:
    return window_indices(t, time_window_size=_DT, stamp=stamp, label="x")  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# The join itself
# --------------------------------------------------------------------------------------


def test_the_two_conventions_index_the_same_window_differently() -> None:
    """A fluid stamp at t=0 and a solid stamp at t=dt are BOTH window 1."""
    fluid = _idx(np.array([0.0, _DT, 2 * _DT]), "window-start")
    solid = _idx(np.array([_DT, 2 * _DT, 3 * _DT]), "window-end")
    assert fluid.tolist() == [1, 2, 3]
    assert solid.tolist() == [1, 2, 3]


def test_the_fluids_trailing_stamp_is_a_window_that_does_not_exist() -> None:
    """The final write after the run closes maps to n+1, and the join drops it."""
    fluid = _idx(np.array([0.0, _DT, 2 * _DT]), "window-start")  # windows 1,2,3
    solid = _idx(np.array([_DT, 2 * _DT]), "window-end")  # windows 1,2
    windows = common_windows({"fluid": fluid, "solid": solid})
    assert windows.tolist() == [1, 2]
    assert select_windows(fluid, windows, label="fluid").tolist() == [0, 1]
    assert select_windows(solid, windows, label="solid").tolist() == [0, 1]


def test_a_record_missing_windows_its_peers_have_is_refused() -> None:
    """An extra window is expected; a HOLE is a truncated participant."""
    fluid = _idx(np.array([0.0, _DT, 2 * _DT]), "window-start")
    solid = _idx(np.array([_DT, 3 * _DT]), "window-end")  # window 2 missing
    with pytest.raises(ScheduleError, match="missing coupling windows"):
        common_windows({"fluid": fluid, "solid": solid})


def test_a_stamp_off_the_window_grid_is_refused_rather_than_rounded() -> None:
    with pytest.raises(ScheduleError, match="off the coupling grid"):
        _idx(np.array([0.0, 0.6 * _DT]), "window-start")


def test_a_repeated_window_is_refused_by_the_selector() -> None:
    """Handed a per-ITERATION record, the selector must not pick a row at random."""
    index = np.asarray([1, 1, 2], dtype=np.int64)
    with pytest.raises(ScheduleError, match="appears more than once"):
        select_windows(index, np.asarray([1, 2], dtype=np.int64), label="force.dat")


def test_the_solid_convention_agrees_with_the_one_ccx_dat_already_encoded() -> None:
    """`assert_matches_schedule` requires rint(t/dt) == 1..n; so does this."""
    solid = _idx(np.asarray([_DT * k for k in range(1, 11)]), "window-end")
    assert solid.tolist() == list(range(1, 11))


# --------------------------------------------------------------------------------------
# The cadence classifier
# --------------------------------------------------------------------------------------


def test_a_window_start_record_needs_the_window_start_stamp() -> None:
    """3 windows, iterations (2,3,4): starts at 0,dt,2dt plus the trailing write at 3dt."""
    t = np.asarray([0.0, 0.0, _DT, _DT, _DT, 2 * _DT, 2 * _DT, 2 * _DT, 2 * _DT, 3 * _DT])
    cadence = classify_repeat_cadence(t, n_windows=3, total_iterations=10, stamp="window-start")
    assert cadence.kind == "per-iteration"
    assert (cadence.n_rows, cadence.n_distinct) == (10, 4)


def test_the_default_stamp_still_classifies_a_window_end_record() -> None:
    """Unchanged for every pre-ADR-040 caller — the default is `window-end`."""
    t = np.asarray([_DT, _DT, 2 * _DT, 2 * _DT, 2 * _DT])
    assert classify_repeat_cadence(t, n_windows=2, total_iterations=5).kind == "per-iteration"


def test_the_wrong_stamp_now_says_so_instead_of_blaming_time_precision() -> None:
    """The old message sent the reader after a deck setting that was already correct."""
    t = np.asarray([0.0, 0.0, _DT, _DT, _DT, 2 * _DT, 2 * _DT, 2 * _DT, 2 * _DT, 3 * _DT])
    with pytest.raises(ValueError, match="OTHER stamp convention") as exc:
        classify_repeat_cadence(t, n_windows=3, total_iterations=10, stamp="window-end")
    assert "timePrecision" not in str(exc.value)
    assert "window-start" in str(exc.value)


def test_a_genuine_precision_collapse_still_names_time_precision() -> None:
    """The old diagnosis is still offered — just no longer for the wrong symptom."""
    t = np.asarray([_DT, _DT, 2 * _DT])
    with pytest.raises(ValueError, match="timePrecision"):
        classify_repeat_cadence(t, n_windows=2, total_iterations=9)


# --------------------------------------------------------------------------------------
# The measurement, on bytes this repo did not write for the test
# --------------------------------------------------------------------------------------


@pytest.mark.skipif(
    not all(p.is_dir() for p in _ALL_RUNS.values()),
    reason="the coupled runs are on the aero NFS mount, which this host does not have",
)
class TestAgainstTheSurvivingI4Bytes:
    """Every claim `precice.schedule` makes, re-derived from the real coupled records.

    Parametrized over FOUR runs, not two. The `i4-*` pair is where the session-9/10 finding
    was made and both are SERIAL. The `q1-*` pair is the ADR-040 equivalence probe, and its
    fluid participant ran DECOMPOSED over four ranks — which is the shape wave 1 will have.
    Under `mpirun` OpenFOAM writes `processor*/<time>` rather than `<time>`, and that one
    level of extra nesting is what made the session-10 disk projection read 1 time directory
    instead of 69 (§6.39). The L-smoke checked that `force.dat` still lands in the case root;
    holding the join itself to the same standard is what these ids add.
    """

    @staticmethod
    def _arm(run: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[float, ...]]:
        case = next((run / "tutorial").glob("hg2007-*-foil"))
        raw = read_force_history(
            case / "fluid-openfoam/postProcessing/forces1/0/force.dat", repeats="raw"
        )
        report = read_iterations_log(
            find_iterations_logs(case)["Fluid"], participant="Fluid", max_iterations_configured=50
        )
        iterations = np.asarray(report.iterations_per_window, dtype=np.int64)
        reaction = read_reaction_forces(
            next((case / "solid-calculix").glob("*.dat")), iterations_per_window=iterations
        )
        return raw.t, raw.pressure[:, 1] + raw.viscous[:, 1], iterations, reaction.t

    @pytest.mark.parametrize("arm", sorted(_ALL_RUNS))
    def test_the_fluid_carries_one_distinct_time_more_than_there_are_windows(
        self, arm: str
    ) -> None:
        t, _, iterations, _ = self._arm(_ALL_RUNS[arm])
        assert t.size == int(iterations.sum())
        assert np.unique(t).size == iterations.size + 1

    @pytest.mark.parametrize("arm", sorted(_ALL_RUNS))
    def test_the_row_count_at_each_stamp_is_that_windows_iteration_count(self, arm: str) -> None:
        """The arithmetic that identifies the convention, exact on 499/500 windows.

        Window 1 carries one row fewer -- the coded function object does not emit on its
        very first execution -- and that deficit does NOT shift the mapping: it is a
        missing row inside window 1, not a row belonging to another window.
        """
        t, _, iterations, _ = self._arm(_ALL_RUNS[arm])
        _, counts = np.unique(t, return_counts=True)
        assert counts[0] == iterations[0] - 1
        n = iterations.size
        assert np.array_equal(counts[1:n], iterations[1:n])
        assert counts[n] == 1

    @pytest.mark.parametrize("arm", sorted(_ALL_RUNS))
    def test_grouping_by_window_start_gives_a_converging_iterate_sequence(self, arm: str) -> None:
        """The decisive check, and the one that rules the alternative grouping out.

        Under the window-START reading, the rows at one stamp are one window's
        fixed-point iteration, so successive |dF| must shrink. Measured: 100 % of windows
        under this grouping, 0 % under the alternative (converged-iterate-at-window-end).
        """
        t, fy, iterations, _ = self._arm(_ALL_RUNS[arm])
        index = _idx(t, "window-start")
        converging = total = 0
        for window in range(1, iterations.size + 1):
            rows = fy[index == window]
            if rows.size < 3:
                continue
            steps = np.abs(np.diff(rows))
            converging += int(np.all(steps[1:] <= steps[:-1] * 1.05))
            total += 1
        assert total > 100, "too few multi-iteration windows to be evidence"
        assert converging == total

    @pytest.mark.parametrize("arm", sorted(_ALL_RUNS))
    def test_the_join_recovers_every_window_and_drops_exactly_one(self, arm: str) -> None:
        t, _, iterations, solid_t = self._arm(_ALL_RUNS[arm])
        fluid = _idx(np.unique(t), "window-start")
        solid = _idx(np.asarray(solid_t), "window-end")
        assert fluid.tolist() == list(range(1, iterations.size + 2))
        assert solid.tolist() == list(range(1, iterations.size + 1))
        windows = common_windows({"force.dat": fluid, "solid reaction": solid})
        assert windows.tolist() == list(range(1, iterations.size + 1))
        assert fluid.size - windows.size == 1

    @pytest.mark.parametrize("arm", sorted(_ALL_RUNS))
    def test_the_decomposition_is_what_the_id_says_it_is(self, arm: str) -> None:
        """Otherwise the `q1-*` ids are the serial claim wearing a decomposed label.

        L2, held to the join's standard: `processor*/` exists on the parallel runs and not
        on the serial ones, and `force.dat` lands in the case root either way.
        """
        case = next((_ALL_RUNS[arm] / "tutorial").glob("hg2007-*-foil"))
        processors = sorted((case / "fluid-openfoam").glob("processor*"))
        assert len(processors) == (4 if arm.startswith("q1-") else 0), [p.name for p in processors]
        assert (case / "fluid-openfoam/postProcessing/forces1/0/force.dat").is_file()

    @pytest.mark.parametrize("arm", sorted(_ALL_RUNS))
    def test_the_old_raw_time_comparison_could_only_ever_have_refused(self, arm: str) -> None:
        """What `--collect` would have done after weeks of wall clock, reproduced."""
        t, _, iterations, solid_t = self._arm(_ALL_RUNS[arm])
        assert np.unique(t).size != len(solid_t), "the shape mismatch is gone; check the fixture"
        with pytest.raises(ValueError, match="OTHER stamp convention"):
            classify_repeat_cadence(
                t, n_windows=iterations.size, total_iterations=int(iterations.sum())
            )
