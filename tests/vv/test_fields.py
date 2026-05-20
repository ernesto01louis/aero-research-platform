"""Stage 05 unit tests for OpenFOAM wall-field extraction — pure, no cluster."""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.fields import FieldExtractionError, extract_wall_distributions

pytestmark = pytest.mark.stage_05


def _write_sample(post: Path, *, time: str = "3000") -> None:
    """Write a synthetic `surfaces` raw sample tree (out-of-order rows)."""
    d = post / "sampleWall" / time
    d.mkdir(parents=True)
    # x y z p — rows deliberately not sorted by x.
    (d / "p_wall.raw").write_text(
        "# x y z p\n0.5 0 0 0.25\n0.0 0 0 0.10\n1.0 0 0 -0.05\n",
        encoding="utf-8",
    )
    # x y z tau_x tau_y tau_z — tau_x negative for attached +x flow.
    (d / "wallShearStress_wall.raw").write_text(
        "# x y z tau_x tau_y tau_z\n"
        "0.5 0 0 -0.0015 0 0\n0.0 0 0 -0.0030 0 0\n1.0 0 0 -0.0010 0 0\n",
        encoding="utf-8",
    )


def test_extract_sorts_and_forms_coefficients(tmp_path: Path) -> None:
    _write_sample(tmp_path)
    wd = extract_wall_distributions(tmp_path, patch="wall")
    assert wd.x == [0.0, 0.5, 1.0]  # sorted ascending
    assert wd.cp == pytest.approx([0.20, 0.50, -0.10])  # Cp = 2 * p
    # Cf = -2 * tau_x  -> positive for attached flow.
    assert wd.cf == pytest.approx([0.0060, 0.0030, 0.0020])
    assert all(c > 0 for c in wd.cf)


def test_extract_uses_latest_time_directory(tmp_path: Path) -> None:
    _write_sample(tmp_path, time="100")
    _write_sample(tmp_path, time="3000")
    wd = extract_wall_distributions(tmp_path, patch="wall")
    assert len(wd.x) == 3


def test_extract_fails_loud_without_output(tmp_path: Path) -> None:
    with pytest.raises(FieldExtractionError, match="no sampled-surface output"):
        extract_wall_distributions(tmp_path, patch="wall")


def test_extract_fails_loud_on_wrong_column_count(tmp_path: Path) -> None:
    d = tmp_path / "sampleWall" / "3000"
    d.mkdir(parents=True)
    (d / "p_wall.raw").write_text("# bad\n0.0 0 0\n0.5 0 0\n", encoding="utf-8")
    (d / "wallShearStress_wall.raw").write_text(
        "0.0 0 0 -0.003 0 0\n0.5 0 0 -0.0015 0 0\n", encoding="utf-8"
    )
    with pytest.raises(FieldExtractionError, match="columns"):
        extract_wall_distributions(tmp_path, patch="wall")
