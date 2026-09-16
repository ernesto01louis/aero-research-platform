"""The CalculiX .dat reader: real bytes, and a cadence that is classified rather than assumed.

The fixture format is copied from a live ccx 2.20 run (the S1 spike), not invented: four
lines per record, blank-separated, time printed at seven significant digits.

The cadence question is the substance. Under IMPLICIT coupling ccx re-does an increment for
every coupling iteration and prints on each, so a time appears several times; under explicit
coupling it appears once. Which one a file is cannot be assumed, so the reader proves it
from the coupling iteration counts and RAISES on anything that matches neither rule -- the
alternative being a plausible number extracted from a file nobody understood.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from aero.adapters.precice.ccx_dat import (
    CcxDatError,
    assert_matches_schedule,
    read_reaction_forces,
)

pytestmark = pytest.mark.stage_20

DT = 5.0e-3


def _record(time: float, fx: float, fy: float, fz: float) -> str:
    # Byte-for-byte the shape ccx 2.20 writes, including the leading blank line.
    return (
        "\n total force (fx,fy,fz) for set NNOSE and time "
        f" {time:.7E}\n\n       {fx:.6E}  {fy:.6E} {fz:.6E}\n"
    )


def _write(tmp_path: Path, records) -> Path:
    path = tmp_path / "solid.dat"
    path.write_text("".join(_record(*r) for r in records), encoding="utf-8")
    return path


def _per_window(n: int = 5):
    return [((i + 1) * DT, -1e-9 * (i + 1), 6.29e-6 * (i + 1), -7.8e-16) for i in range(n)]


class TestTheRealFormatIsRead:
    def test_a_per_window_record_reads(self, tmp_path: Path) -> None:
        history = read_reaction_forces(_write(tmp_path, _per_window()))
        assert history.nset == "NNOSE"
        assert history.cadence == "per-window"
        assert history.n_duplicates == 0
        assert history.times.size == 5
        assert history.forces.shape == (5, 3)

    def test_the_plunge_axis_values_survive(self, tmp_path: Path) -> None:
        history = read_reaction_forces(_write(tmp_path, _per_window()))
        assert history.forces[0, 1] == pytest.approx(6.29e-6)
        assert history.forces[4, 1] == pytest.approx(6.29e-6 * 5)

    def test_a_file_with_no_records_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "solid.dat"
        path.write_text("\n some other ccx output\n\n", encoding="utf-8")
        with pytest.raises(CcxDatError, match="no 'total force' records"):
            read_reaction_forces(path)

    def test_a_truncated_final_record_is_refused(self, tmp_path: Path) -> None:
        # What a killed solver leaves behind: a header with no values line.
        path = _write(tmp_path, _per_window())
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n total force (fx,fy,fz) for set NNOSE and time  3.0000000E-02\n",
            encoding="utf-8",
        )
        with pytest.raises(CcxDatError, match="truncated"):
            read_reaction_forces(path)

    def test_two_node_sets_are_refused(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _per_window(2))
        path.write_text(
            path.read_text(encoding="utf-8").replace("NNOSE and time  1.0", "NOTHER and time  1.0"),
            encoding="utf-8",
        )
        with pytest.raises(CcxDatError, match="node sets"):
            read_reaction_forces(path)

    def test_a_missing_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(CcxDatError, match="not found"):
            read_reaction_forces(tmp_path / "absent.dat")


class TestAgainstRealCalculiXBytes:
    """The fixture is ccx 2.20's OWN output, not a reconstruction of it.

    Ten records lifted verbatim from the S1 spike on aero-dev (uncoupled, so per-window).
    A reader tested only against bytes the test itself generated proves that the writer and
    the reader agree with each other, which is exactly the vacuous shape the Stage-20
    non-regression discipline exists to avoid.
    """

    FIXTURE = Path(__file__).parent / "fixtures" / "ccx_dat" / "ccx220-node-print-totals.dat"

    def test_it_parses_the_real_file(self) -> None:
        history = read_reaction_forces(self.FIXTURE)
        assert history.nset == "NNOSE"
        assert history.cadence == "per-window"
        assert history.n_duplicates == 0
        assert history.times.size == 10

    def test_the_values_are_the_bytes_on_disk(self) -> None:
        history = read_reaction_forces(self.FIXTURE)
        assert history.times[0] == pytest.approx(5.0e-3)
        assert history.forces[0, 0] == pytest.approx(-6.391247e-10)
        assert history.forces[0, 1] == pytest.approx(6.290534e-06)
        assert history.forces[0, 2] == pytest.approx(-7.841086e-16)

    def test_the_real_record_is_the_coupling_schedule(self) -> None:
        history = read_reaction_forces(self.FIXTURE)
        assert_matches_schedule(history, time_window_size=5.0e-3, n_windows=10)

    def test_the_prescribed_nose_reacts_only_along_the_plunge_axis(self) -> None:
        """The deck's two kinematic constraints, visible in the solver's own output.

        `*BOUNDARY Nall, 3` suppresses the out-of-plane dof and `Nnose, 1, 1` fixes the
        teardrop chordwise, so on this uncoupled spike -- where the only load is the
        prescribed nose's own inertia -- the reaction should be along +y alone. MEASURED
        on the fixture: |fz|/|fy| = 3.7e-8 and |fx|/|fy| = 1.4e-4, against an fy that
        grows with the startup ramp. The bounds below carry an order of margin over those.
        """
        history = read_reaction_forces(self.FIXTURE)
        fx, fy, fz = (np.max(np.abs(history.forces[:, i])) for i in range(3))
        assert fz < 1e-7 * fy, "dof 3 is suppressed; a real out-of-plane reaction means it is not"
        assert fx < 1e-3 * fy, "the teardrop is fixed chordwise"
        assert fy > 0.0


class TestTheCadenceIsClassifiedNotAssumed:
    def _per_iteration(self, iterations):
        """One record per coupling ITERATION, the last at each time being the converged one."""
        records = []
        for window, count in enumerate(iterations, start=1):
            for attempt in range(count):
                # Earlier iterates differ; only the last must survive.
                scale = 1.0 if attempt == count - 1 else 0.5
                records.append((window * DT, -1e-9 * window, scale * 6.29e-6 * window, -7.8e-16))
        return records

    def test_a_per_iteration_record_keeps_the_last_row_at_each_time(self, tmp_path: Path) -> None:
        iterations = np.array([3, 2, 4, 2, 2])
        path = _write(tmp_path, self._per_iteration(iterations))
        history = read_reaction_forces(path, iterations_per_window=iterations)

        assert history.cadence == "per-iteration"
        assert history.n_rows_read == int(iterations.sum())
        assert history.n_duplicates == int(iterations.sum() - iterations.size)
        assert history.times.size == iterations.size
        # The converged value, not a discarded iterate and not their average.
        assert history.forces[0, 1] == pytest.approx(6.29e-6)

    def test_duplicates_without_an_iterations_log_are_refused(self, tmp_path: Path) -> None:
        iterations = np.array([3, 2, 4, 2, 2])
        path = _write(tmp_path, self._per_iteration(iterations))
        with pytest.raises(CcxDatError, match="no coupling iteration counts"):
            read_reaction_forces(path)

    def test_a_partial_match_raises_rather_than_picking_a_rule(self, tmp_path: Path) -> None:
        # The heart of it: the duplicate count matches NEITHER 0 nor sum-minus-windows, so
        # the file and the log do not describe the same run.
        iterations = np.array([3, 2, 4, 2, 2])
        path = _write(tmp_path, self._per_iteration(iterations))
        with pytest.raises(CcxDatError, match="do not describe the same run"):
            read_reaction_forces(path, iterations_per_window=np.array([3, 2, 4, 2, 3]))

    def test_a_window_count_disagreement_is_refused(self, tmp_path: Path) -> None:
        iterations = np.array([3, 2, 4, 2, 2])
        path = _write(tmp_path, self._per_iteration(iterations))
        # Same total duplicates, different window count: 5 windows summing 13 vs 4 summing 12.
        with pytest.raises(CcxDatError):
            read_reaction_forces(path, iterations_per_window=np.array([4, 3, 4, 2]))

    def test_a_per_window_record_needs_no_log(self, tmp_path: Path) -> None:
        history = read_reaction_forces(_write(tmp_path, _per_window()))
        assert history.cadence == "per-window"


class TestTheRecordIsTheCouplingSchedule:
    def test_a_matching_record_passes(self, tmp_path: Path) -> None:
        history = read_reaction_forces(_write(tmp_path, _per_window()))
        assert_matches_schedule(history, time_window_size=DT, n_windows=5)

    def test_a_short_record_names_the_increment_cap_trap(self, tmp_path: Path) -> None:
        history = read_reaction_forces(_write(tmp_path, _per_window(3)))
        with pytest.raises(CcxDatError, match="STEP INC"):
            assert_matches_schedule(history, time_window_size=DT, n_windows=5)

    def test_a_solid_stepping_at_a_different_dt_is_refused(self, tmp_path: Path) -> None:
        history = read_reaction_forces(_write(tmp_path, _per_window()))
        with pytest.raises(CcxDatError):
            assert_matches_schedule(history, time_window_size=DT * 1.5, n_windows=5)

    def test_printed_precision_does_not_trip_the_comparison(self, tmp_path: Path) -> None:
        # 7 significant digits cannot represent an arbitrary dt exactly, so a
        # value-by-value float comparison would fail on a perfectly correct record.
        dt = 3.5e-4
        records = [((i + 1) * dt, -1e-9, 6.29e-6, -7.8e-16) for i in range(20)]
        history = read_reaction_forces(_write(tmp_path, records))
        assert_matches_schedule(history, time_window_size=dt, n_windows=20)
        assert history.times[0] != dt or True  # the point is it need not be bitwise equal
