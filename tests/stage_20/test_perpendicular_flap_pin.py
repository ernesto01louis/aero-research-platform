"""Stage 20 — the perpendicular-flap pin is intact and separate from Stage 19's.

Runs in the required unit job: everything checked here is git-tracked, so no
`dvc pull` and no cluster are needed.

The two properties worth pinning mechanically:

1. **The Stage-19 archive is untouched.** Its sha256 is `TutorialPin.archive_sha256`
   in the FSI3 case spec and its manifest backs a closed, tagged verdict. Extending
   it to hold the CalculiX case — the obvious shortcut — would have changed that
   digest and retroactively invalidated the Stage-19 record.
2. **The smoke's manifest actually contains a coupled CalculiX case.** A manifest
   that silently lost `solid-calculix/` would still be a valid CSV, and the failure
   would surface much later, inside a container.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FSI3 = _REPO_ROOT / "data/references/fsi/turek_hron_fsi3"
_FLAP = _REPO_ROOT / "data/references/fsi/precice_perpendicular_flap"


def _manifest(directory: Path) -> dict[str, str]:
    text = (directory / "tutorials_pin_manifest.csv").read_text(encoding="utf-8")
    rows = csv.DictReader(line for line in text.splitlines() if not line.startswith("#"))
    return {row["path"]: row["sha256"] for row in rows}


def test_the_two_pins_are_separate_artifacts() -> None:
    fsi3 = _FSI3 / "precice-tutorials-turek-hron-fsi3.tar.gz.sha256"
    flap = _FLAP / "precice-tutorials-perpendicular-flap.tar.gz.sha256"
    assert fsi3.read_text().strip() != flap.read_text().strip()


def test_the_stage_19_manifest_carries_no_perpendicular_flap_files() -> None:
    """The FSI3 integrity contract must not have been widened."""
    assert not [p for p in _manifest(_FSI3) if p.startswith("perpendicular-flap/")]


def test_the_smoke_manifest_carries_a_coupled_calculix_case() -> None:
    paths = _manifest(_FLAP)
    for required in (
        "perpendicular-flap/precice-config.xml",
        "perpendicular-flap/solid-calculix/config.yml",
        "perpendicular-flap/solid-calculix/flap.inp",
        "perpendicular-flap/solid-calculix/all.msh",
        "perpendicular-flap/solid-calculix/interface_beam.nam",
        "perpendicular-flap/fluid-openfoam/system/preciceDict",
        "perpendicular-flap/fluid-openfoam/system/blockMeshDict",
    ):
        assert required in paths, required


def test_tools_is_vendored_because_upstream_run_sh_sources_outside_the_case() -> None:
    """Stage-19 gotcha 11: `run.sh` sources `../../tools/log.sh`."""
    assert "tools/log.sh" in _manifest(_FLAP)


def test_both_pins_are_the_same_upstream_commit() -> None:
    """The conventions the smoke teaches must be the ones the gated case inherits."""
    commit = "cd33e2dbacc5a2f4a1202e215890f54a2ce2e79e"
    for directory in (_FSI3, _FLAP):
        header = (directory / "tutorials_pin_manifest.csv").read_text(encoding="utf-8")
        assert commit in header, directory


def test_shared_files_agree_between_the_two_manifests() -> None:
    """`tools/` is vendored twice, from one commit — the digests must match.

    A disagreement would mean one of the two archives was built from a different
    tree than its header claims.
    """
    fsi3, flap = _manifest(_FSI3), _manifest(_FLAP)
    shared = set(fsi3) & set(flap)
    assert shared, "the two manifests should share tools/"
    assert {p: fsi3[p] for p in shared} == {p: flap[p] for p in shared}
