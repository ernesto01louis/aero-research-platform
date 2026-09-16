"""ADR-045 R1/F3 as accepted (amendment A1): the record moves, the numbers do not.

Two rendered bytes change for the checkpoint/restart family -- the solid deck's
``*AMPLITUDE`` card carries ``TIME=TOTAL TIME`` (a restarted ``*STEP`` must not replay the
plunge from zero) and the fluid's ``controlDict`` writes fields at ``writePrecision 17`` (a
double round-trips through a restart). Neither moves a number in an unrestarted run: in a
single step from ``ttime = 0`` step time and total time are the same quantity, and a wider
write precision changes only what is written back to disk.

``config_hash`` digests the serialized spec and never the rendered bytes, so the RECORD
moves through ``RENDERER_VERSION`` -- bumped to "2" in the same commit, with every live
digest re-pinned beside it (``test_n3_live_submission_digest_is_pinned.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.flexible_foil import write_flexible_foil_case
from aero.adapters.precice.calculix import (
    AmplitudeTable,
    CalculiXDeckError,
    _amplitude_text,
    assert_calculix_deck,
    read_calculix_deck,
    write_calculix_deck,
)
from aero.adapters.precice.template import RENDERER_VERSION
from aero.vv.fsi.hg2007_flexible_foil import hg2007_case_spec

pytestmark = pytest.mark.stage_20

_KNOBS = {
    "arm": "flexible",
    "rung": "mid",
    "time_window_size": 2e-05,
    "max_time": 0.001,  # 50 windows: enough deck to read back, small enough to render fast
    "wall_clock_ceiling_s": 3600,
    "numerics_label": "adr040-candidate",
    "mpi_ranks": 4,
    "hht_alpha": -0.05,
}


def test_the_renderer_version_is_two_and_names_the_adr() -> None:
    assert RENDERER_VERSION == "2"


def test_the_amplitude_card_is_indexed_by_total_time(tmp_path: Path) -> None:
    spec = hg2007_case_spec(**_KNOBS)  # type: ignore[arg-type]
    deck = write_calculix_deck(spec.source.solid, dest_dir=tmp_path)
    first = (tmp_path / "plunge.amp").read_text(encoding="utf-8").splitlines()[0]
    assert first == "*AMPLITUDE, NAME=PLUNGE, TIME=TOTAL TIME"
    assert deck.amplitude.time_base == "TOTAL TIME"


def test_the_deck_bytes_differ_from_the_previous_renderer_only_in_that_token() -> None:
    table = AmplitudeTable(
        name="PLUNGE", n_rows=3, t=(0.0, 1.0, 2.0), value=(0.0, 0.5, 0.0), time_base="TOTAL TIME"
    )
    legacy = table.model_copy(update={"time_base": "STEP TIME"})
    assert _amplitude_text(table).replace(", TIME=TOTAL TIME", "") == _amplitude_text(legacy)
    assert _amplitude_text(legacy).splitlines()[0] == "*AMPLITUDE, NAME=PLUNGE"


def test_a_deck_without_the_token_is_refused_by_the_self_check(tmp_path: Path) -> None:
    """The trap R1 names: a step-time table replays the plunge on restart, silently."""
    spec = hg2007_case_spec(**_KNOBS)  # type: ignore[arg-type]
    write_calculix_deck(spec.source.solid, dest_dir=tmp_path)
    amp = tmp_path / "plunge.amp"
    amp.write_text(
        amp.read_text(encoding="utf-8").replace(", TIME=TOTAL TIME", "", 1), encoding="utf-8"
    )
    deck = read_calculix_deck(tmp_path / "hg2007-flexible-solid.inp")
    assert deck.amplitude.time_base == "STEP TIME"
    with pytest.raises(CalculiXDeckError, match="amplitude time base"):
        assert_calculix_deck(deck, spec.source.solid)


def test_the_parser_accepts_calculix_blank_stripped_spelling(tmp_path: Path) -> None:
    spec = hg2007_case_spec(**_KNOBS)  # type: ignore[arg-type]
    write_calculix_deck(spec.source.solid, dest_dir=tmp_path)
    amp = tmp_path / "plunge.amp"
    amp.write_text(
        amp.read_text(encoding="utf-8").replace("TIME=TOTAL TIME", "TIME=TOTALTIME", 1),
        encoding="utf-8",
    )
    assert read_calculix_deck(tmp_path / "hg2007-flexible-solid.inp").amplitude.time_base == (
        "TOTAL TIME"
    )


def test_the_fluid_writes_fields_at_seventeen_digits(tmp_path: Path) -> None:
    spec = hg2007_case_spec(**_KNOBS)  # type: ignore[arg-type]
    write_flexible_foil_case(spec.source.fluid, tmp_path)
    control = (tmp_path / "system" / "controlDict").read_text(encoding="utf-8")
    assert "writePrecision  17;" in control
    assert "writeFormat     ascii;" in control
