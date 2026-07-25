"""Stage 18 — STEP ingestion round-trip through the CAD extra (ADR-033).

Gated on `aero[cad]` being installed (build123d) — no binary STEP fixture lives in the
repo: the test authors a primitive with the kernel, exports STEP, and pulls it back
through the exact same `ingest()` gate path an operator would use.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.geometry import IngestConfig, ingest

pytestmark = pytest.mark.stage_18


def test_step_box_round_trips_through_the_gate(cad_extra_installed: bool, tmp_path: Path) -> None:
    if not cad_extra_installed:
        pytest.skip("aero[cad] not installed (build123d)")
    from build123d import Box, export_step

    box = Box(10.0, 5.0, 2.0)
    step_path = tmp_path / "box.step"
    export_step(box, str(step_path))

    record = ingest(step_path, config=IngestConfig())
    assert record.fmt == "step"
    assert record.quality.watertight
    assert record.quality.manifold
    assert record.quality.orientation_consistent
    assert record.quality.n_intersecting_pairs == 0
    # Tessellated box volume must match the exact solid.
    assert record.quality.signed_volume == pytest.approx(100.0, rel=1e-6)


def test_step_loader_absent_extra_raises_actionably(
    cad_extra_installed: bool, tmp_path: Path
) -> None:
    if cad_extra_installed:
        pytest.skip("aero[cad] installed — the ImportError path is not reachable")
    fake = tmp_path / "anything.step"
    fake.write_text("ISO-10303-21;")
    with pytest.raises(ImportError, match=r"aero\[cad\]"):
        ingest(fake)
