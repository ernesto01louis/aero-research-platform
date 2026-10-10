"""The template's coupling numerics agree with the UPSTREAM bytes they were copied from.

Session-7 adversarial review, candidate 1: the template comment claims its numerics are
"taken verbatim from precice/tutorials @ cd33e2db perpendicular-flap/precice-config.xml",
and every existing assertion checks the template against ``template.py``'s module
constants — two copies of one transcription, which pass together whenever both are wrong
the same way. This test closes the loop against the pinned archive itself, through the
platform's own parser, so a transcription slip is caught by the third, independent copy.

Candidate 2 rides along: the expectation's watch-point keys must be DERIVED from the
exported name constants, because ``solver.py`` builds the watch-point log paths from
those constants and a hand-typed literal was a third copy nothing tied down.

Lives in ``tests/stage_20`` (not CI): the archive is DVC-tracked and a runner without a
``dvc pull`` must skip, not fail. It runs in the mandated local suite.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest
from aero.adapters.precice import template as tpl
from aero.adapters.precice.config import read_precice_config

pytestmark = pytest.mark.stage_20

_ARCHIVE = (
    Path(__file__).resolve().parents[2]
    / "data/references/fsi/precice_perpendicular_flap/precice-tutorials-perpendicular-flap.tar.gz"
)


def _upstream_config(tmp_path_factory_dir: Path):  # type: ignore[no-untyped-def]
    if not _ARCHIVE.exists():
        pytest.skip(f"pinned archive not pulled: {_ARCHIVE}")
    with tarfile.open(_ARCHIVE, "r:gz") as archive:
        member = next(
            m
            for m in archive.getmembers()
            if m.name.endswith("perpendicular-flap/precice-config.xml")
        )
        handle = archive.extractfile(member)
        assert handle is not None
        text = handle.read().decode("utf-8")
    extracted = tmp_path_factory_dir / "upstream-precice-config.xml"
    extracted.write_text(text, encoding="utf-8")
    return read_precice_config(extracted)


def test_the_coupling_numerics_are_upstreams_own(tmp_path: Path) -> None:
    model = _upstream_config(tmp_path)
    scheme = model.coupling_scheme
    assert scheme.kind == "parallel-implicit"
    assert scheme.max_iterations == tpl._MAX_ITERATIONS
    for measure in scheme.convergence_measures:
        assert measure.kind == tpl._CONVERGENCE_KIND
        assert measure.limit == tpl._CONVERGENCE_LIMIT
    acceleration = scheme.acceleration
    assert acceleration is not None
    assert acceleration.kind == tpl._ACCELERATION_KIND
    assert acceleration.filter_type == tpl._ACCELERATION_FILTER_TYPE
    assert acceleration.filter_limit == tpl._ACCELERATION_FILTER_LIMIT
    assert acceleration.initial_relaxation == tpl._ACCELERATION_INITIAL_RELAXATION
    assert acceleration.max_used_iterations == tpl._ACCELERATION_MAX_USED_ITERATIONS
    assert acceleration.time_windows_reused == tpl._ACCELERATION_TIME_WINDOWS_REUSED


def test_the_expectations_watch_point_keys_derive_from_the_constants() -> None:
    values = tpl.PreciceConfigValues(
        time_window_size=1.0e-3,
        max_time=1.0,
        support_radius=0.01,
        nose_watch_point=(0.0, 0.0),
        te_watch_point=(0.09, 0.0),
        exchange_directory="case",
    )
    expectation = tpl.hg2007_expectation(values)
    assert set(expectation.watch_points) == {
        f"Solid/{tpl.NOSE_WATCH_POINT_NAME}",
        f"Solid/{tpl.TE_WATCH_POINT_NAME}",
    }
