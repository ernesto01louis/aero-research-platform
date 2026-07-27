"""The reference of record must be reproducible from the published series.

This is the check that makes ADR-036 R3 ("the reference is recomputed with the
platform's own estimators") auditable rather than a claim in a document: it re-derives
`fsi3_recomputed.csv` from the DVC-tracked featflow series and compares, and it
independently re-runs the R2 agreement against the published table.

Needs `dvc pull` for `data/references/fsi/turek_hron_fsi3/` — hence `stage_19` rather
than `tests/unit`.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

pytestmark = [pytest.mark.stage_19, pytest.mark.slow]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REFERENCE_DIR = _REPO_ROOT / "data" / "references" / "fsi" / "turek_hron_fsi3"
_SERIES = _REFERENCE_DIR / "ref_fsi3.point"
_RECOMPUTED = _REFERENCE_DIR / "fsi3_recomputed.csv"


def _read_recomputed() -> dict[str, float]:
    lines = [
        ln for ln in _RECOMPUTED.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")
    ]
    return {row["quantity"]: float(row["value"]) for row in csv.DictReader(lines)}


@pytest.fixture(scope="module")
def series_available() -> bool:
    return _SERIES.is_file()


def test_recomputation_is_reproducible(series_available: bool) -> None:
    """Re-derive every value in fsi3_recomputed.csv from ref_fsi3.point."""
    if not series_available:
        pytest.skip(f"{_SERIES} not pulled — run `dvc pull`")

    import sys

    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    from stage19_acquire_fsi_reference import (  # type: ignore[import-not-found]
        _read_point,
        recompute,
    )

    got = recompute(_read_point(_SERIES))
    recorded = _read_recomputed()

    for quantity, value in (
        ("frequency", got.f0),
        ("uy_amplitude", got.uy_amplitude),
        ("ux_amplitude", got.ux_amplitude),
        ("ux_mean", got.ux_mean),
        ("ux_frequency", got.ux_frequency),
        ("uy_mean", got.uy_mean),
        ("drag_mean", got.drag_mean),
        ("drag_amplitude", got.drag_amplitude),
        ("lift_mean", got.lift_mean),
        ("lift_amplitude", got.lift_amplitude),
    ):
        assert value == pytest.approx(recorded[quantity], rel=1e-6), (
            f"{quantity} drifted from the committed reference of record"
        )


def test_r2_agreement_with_the_published_table(series_available: bool) -> None:
    """The recomputation must still agree with featflow level 4 inside the R2 bounds.

    Independent of the acquisition script's own reporting: if this ever fails, the
    reference is not what we think it is and no campaign should be gated against it.
    """
    if not series_available:
        pytest.skip(f"{_SERIES} not pulled — run `dvc pull`")

    table_lines = [
        ln
        for ln in (_REFERENCE_DIR / "fsi3_reference.csv").read_text(encoding="utf-8").splitlines()
        if not ln.startswith("#")
    ]
    level4 = next(
        row
        for row in csv.DictReader(table_lines)
        if row["level"] == "4" and float(row["dt"]) == 2.5e-4
    )
    recorded = _read_recomputed()

    def relative(measured: float, reference: float) -> float:
        return abs(measured - reference) / abs(reference)

    assert relative(recorded["ux_mean"], float(level4["ux_mean"])) <= 0.03
    assert relative(recorded["uy_amplitude"], float(level4["uy_amplitude"])) <= 0.03
    assert relative(recorded["frequency"], float(level4["uy_frequency"])) <= 0.05


def test_the_streamwise_response_is_the_second_harmonic(series_available: bool) -> None:
    """Structural: the whole segmentation rule rests on this being true of the physics."""
    if not series_available:
        pytest.skip(f"{_SERIES} not pulled — run `dvc pull`")
    recorded = _read_recomputed()
    assert recorded["ux_frequency"] / recorded["frequency"] == pytest.approx(2.0, rel=0.02)
