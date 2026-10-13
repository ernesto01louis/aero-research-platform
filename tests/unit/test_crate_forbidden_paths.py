"""Crates never touch ``data/vv/``, never carry the ADR-045 records, never fill a B-sentinel.

The two Stage-20 records ``data/vv/stage20_adr045_r3.json`` and
``data/vv/stage20_n3_confirmation.json`` must NEVER exist: their absence is load-bearing, because
the R7 gate refuses a gated restarted solve on it. ``tests/unit/test_adr045_r3_record_stays_absent.py``
pins that. A crate writer is exactly the kind of new code that could recreate them by accident,
so it refuses every route there.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from aero.crate import CratePathError, EvidenceFile, build_crate, write_crate

from tests.unit._crate_fixtures import built, evidence_only

pytestmark = pytest.mark.stage_21

REPO = Path(__file__).resolve().parents[2]
ADR045 = (
    REPO / "data" / "vv" / "stage20_adr045_r3.json",
    REPO / "data" / "vv" / "stage20_n3_confirmation.json",
)


@pytest.mark.parametrize(
    "dest",
    [
        "data/vv/some-crate",
        "data/vv/sub/dir/crate",
        "data/../data/vv/x",
    ],
)
def test_a_destination_under_data_vv_is_refused(dest: str, tmp_path: Path) -> None:
    with pytest.raises(CratePathError, match="data/vv"):
        write_crate(tmp_path / dest, built("evidence_only"))


@pytest.mark.parametrize("name", ["stage20_adr045_r3.json", "stage20_n3_confirmation.json"])
def test_the_adr045_names_are_refused_as_destinations_and_members(
    name: str, tmp_path: Path
) -> None:
    with pytest.raises(CratePathError):
        write_crate(tmp_path / name, built("evidence_only"))
    spec = evidence_only()
    ev = EvidenceFile(name=name, data=b"{}\n", media_type="application/json", description="x")
    with pytest.raises(CratePathError):
        build_crate(replace(spec, evidence=(*spec.evidence, ev)))


def test_a_b_sentinel_cannot_ride_in_a_crate() -> None:
    spec = evidence_only()
    ev = EvidenceFile(
        name="sentinel.txt", data=b"<<B1-PENDING-N3>>\n", media_type="text/plain", description="x"
    )
    with pytest.raises(CratePathError, match="B-sentinel"):
        build_crate(replace(spec, evidence=(*spec.evidence, ev)))


def test_an_existing_destination_is_not_overwritten_by_default(tmp_path: Path) -> None:
    write_crate(tmp_path / "c", built("evidence_only"))
    with pytest.raises(CratePathError, match="exists"):
        write_crate(tmp_path / "c", built("evidence_only"))
    write_crate(tmp_path / "c", built("evidence_only"), replace=True)


def test_the_adr045_records_are_still_absent() -> None:
    for path in ADR045:
        assert not path.exists(), path
