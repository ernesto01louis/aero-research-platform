"""Stage 11 — aero.postprocess.forces (closure-checked viscous/pressure split)."""

from __future__ import annotations

import pytest
from aero.postprocess import ForceDecomposition, decompose_drag

pytestmark = pytest.mark.stage_11


def test_force_decomposition_closes() -> None:
    fd = ForceDecomposition(total=0.0096, pressure=0.003, viscous=0.0066)
    assert fd.pressure + fd.viscous == pytest.approx(fd.total)


def test_force_decomposition_fails_loud_when_open() -> None:
    with pytest.raises(ValueError, match="does not close"):
        ForceDecomposition(total=0.05, pressure=0.003, viscous=0.0066)


def test_decompose_drag_projects_and_normalises() -> None:
    # q_aref = 0.5; pressure/viscous forces 0.0015/0.0033 -> Cd 0.003/0.0066.
    fd = decompose_drag(
        pressure_force=(0.0015, 0.0),
        viscous_force=(0.0033, 0.0),
        direction=(1.0, 0.0),
        q_aref=0.5,
        total=0.0096,
    )
    assert fd.pressure == pytest.approx(0.003)
    assert fd.viscous == pytest.approx(0.0066)


def test_decompose_drag_projects_onto_direction() -> None:
    # drag direction straight up -> picks the y-component of each vector.
    fd = decompose_drag(
        pressure_force=(0.0, 0.004),
        viscous_force=(0.005, 0.0),
        direction=(0.0, 1.0),
        q_aref=1.0,
        total=0.004,
    )
    assert fd.pressure == pytest.approx(0.004)
    assert fd.viscous == pytest.approx(0.0)


def test_decompose_drag_fails_loud_on_layout_mismatch() -> None:
    with pytest.raises(ValueError, match="does not close"):
        decompose_drag(
            pressure_force=(0.0015, 0.0),
            viscous_force=(0.0033, 0.0),
            direction=(1.0, 0.0),
            q_aref=0.5,
            total=0.05,  # inconsistent with the projected 0.0096
        )
