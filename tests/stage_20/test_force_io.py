"""The promoted force readers, and the drop count that used to be invisible.

`strictly_increasing_mask` exists because a `Signal` needs strictly-ascending time and
OpenFOAM's force FO can emit duplicate timestamps. That de-duplication is correct, but it
was also SILENT: at `timePrecision 6` (the default) two rows whose true times differ by
less than the printed precision collapse to the same string and one is deleted. At the
Stage-11/13 write intervals that never happened; at Stage 20's coupling time-window size
it happens routinely, and the result is a force record with holes that segments into
cycles perfectly happily and reports means computed from the wrong samples.

So the reader now reports `n_dropped`, and the Stage-20 readout raises on a non-zero
count rather than each caller rediscovering the trap. These tests pin both halves: the
de-duplication still does what it did, and it now says so.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from aero.adapters.openfoam.force_io import (
    read_coefficient_dat,
    read_force_history,
    strictly_increasing_mask,
)

pytestmark = pytest.mark.stage_20

# The OLDER parenthesised layout: ((pressure)(viscous)(porous)) — no total group, which
# is why the reader takes the FIRST group as pressure here and the SECOND triple of the
# flat layout below. The two branches disagree about which group is which precisely
# because the two formats do.
_PARENTHESISED = """\
# Time forces(pressure viscous porous) moment(...)
0.001 ((0.1 0.2 0) (0.01 0.02 0) (0 0 0)) ((0 0 0) (0 0 0) (0 0 0))
0.002 ((0.2 0.3 0) (0.02 0.03 0) (0 0 0)) ((0 0 0) (0 0 0) (0 0 0))
0.003 ((0.3 0.4 0) (0.03 0.04 0) (0 0 0)) ((0 0 0) (0 0 0) (0 0 0))
"""

# What OpenFOAM-ESI v2412 ACTUALLY writes on this platform, header and spacing copied from
# a real run (plunging_airfoil_hg2007_st02_lm, aero-dev): a flat layout whose first triple
# is the TOTAL. Rows 2 and 3 carry the same time string, which is what a dt smaller than
# `timePrecision` produces — and what the de-duplication then silently deleted.
_COLLAPSED = """\
# Force
# CofR          : (2.50000000e-01 0.00000000e+00 0.00000000e+00)
#
# Time          \ttotal_x total_y total_z\tpressure_x pressure_y pressure_z\tviscous_x viscous_y viscous_z
0.001 0.11 0.22 0 0.1 0.2 0 0.01 0.02 0
0.002 0.22 0.33 0 0.2 0.3 0 0.02 0.03 0
0.002 0.99 0.99 0 0.9 0.9 0 0.09 0.09 0
0.003 0.33 0.44 0 0.3 0.4 0 0.03 0.04 0
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "force.dat"
    path.write_text(text, encoding="utf-8")
    return path


class TestTheReaderIsUnchanged:
    def test_it_reads_the_parenthesised_layout(self, tmp_path: Path) -> None:
        history = read_force_history(_write(tmp_path, _PARENTHESISED))
        assert np.allclose(history.t, [0.001, 0.002, 0.003])
        assert np.allclose(history.pressure, [[0.1, 0.2], [0.2, 0.3], [0.3, 0.4]])
        assert np.allclose(history.viscous, [[0.01, 0.02], [0.02, 0.03], [0.03, 0.04]])

    def test_it_reads_the_flat_layout_this_platform_actually_writes(self, tmp_path: Path) -> None:
        # The flat layout leads with the TOTAL, so pressure is columns 4-6 and viscous 7-9.
        history = read_force_history(_write(tmp_path, _COLLAPSED))
        assert np.allclose(history.t, [0.001, 0.002, 0.003])
        assert np.allclose(history.pressure, [[0.1, 0.2], [0.2, 0.3], [0.3, 0.4]])
        assert np.allclose(history.viscous, [[0.01, 0.02], [0.02, 0.03], [0.03, 0.04]])

    def test_an_empty_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no data rows"):
            read_force_history(_write(tmp_path, "# header only\n"))

    def test_the_mask_still_dedupes(self) -> None:
        t = np.array([0.0, 0.1, 0.1, 0.2, 0.15, 0.3])
        assert list(strictly_increasing_mask(t)) == [True, True, False, True, False, True]

    def test_the_mask_handles_an_empty_series(self) -> None:
        assert strictly_increasing_mask(np.array([])).size == 0


class TestTheDropCountIsVisible:
    def test_a_clean_record_drops_nothing(self, tmp_path: Path) -> None:
        assert read_force_history(_write(tmp_path, _PARENTHESISED)).n_dropped == 0

    def test_a_collapsed_timestamp_is_counted(self, tmp_path: Path) -> None:
        history = read_force_history(_write(tmp_path, _COLLAPSED))
        assert history.n_dropped == 1
        assert history.t.size == 3

    def test_the_dropped_row_is_the_later_duplicate(self, tmp_path: Path) -> None:
        # Which one survives matters: keeping the FIRST row at each new maximum time means
        # the retained sample is the one the solver wrote first, not a re-written value.
        history = read_force_history(_write(tmp_path, _COLLAPSED))
        assert np.allclose(history.pressure[1], [0.2, 0.3])

    def test_the_count_cannot_be_dropped_by_unpacking(self, tmp_path: Path) -> None:
        # A tuple's fourth element is exactly what a caller written by analogy with the old
        # three-element unpacking would silently discard.
        history = read_force_history(_write(tmp_path, _COLLAPSED))
        with pytest.raises(TypeError):
            _t, _p, _v = history  # type: ignore[misc]


class TestTheCoefficientReader:
    def test_it_reads_the_last_comment_line_as_the_header(self, tmp_path: Path) -> None:
        path = tmp_path / "coefficient.dat"
        path.write_text("# junk\n# Time Cd Cl\n0.1 0.01 0.5\n0.2 0.02 0.6\n", encoding="utf-8")
        columns, data = read_coefficient_dat(path)
        assert columns == ["Time", "Cd", "Cl"]
        assert data.shape == (2, 3)

    def test_a_file_without_cd_and_cl_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "coefficient.dat"
        path.write_text("# Time Cm\n0.1 0.01\n", encoding="utf-8")
        with pytest.raises(ValueError, match="unexpected coefficient-file columns"):
            read_coefficient_dat(path)
