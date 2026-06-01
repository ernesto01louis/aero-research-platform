"""Stage 08 — DrivAerNet++ structural quarantine (ADR-008 §D4) tests.

Three-layer defence:

1. Structural separator — verified by `non-commercial-fence.yml` CI; not
   re-tested here (CI handles cross-source-tree scans).
2. Constructor guard — `LicenseAcknowledgmentRequired` raises without
   `acknowledge_noncommercial=True`.
3. Tainted-sample union — `__getitem__` yields ``TaintedSample`` which
   flips the surrogate's ``_non_commercial`` flag and forces the issued
   cert to carry ``non_commercial=True``.
"""

# non-commercial: justified — quarantine tests live here intentionally.

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aero.surrogates._common.base import TaintedSample
from aero.surrogates._common.certificate import LicenseAcknowledgmentRequired
from aero.surrogates._common.loaders import DatasetLoaderError
from aero.surrogates._common.loaders.non_commercial.drivaernet_plus_plus import (
    DATASET_ID,
    LICENSE_ID,
    DrivAerNetPlusPlusDataset,
)

pytestmark = pytest.mark.stage_08

_SAMPLE_MANIFEST = [
    {
        "case_id": "npp-001",
        "body_type": "fastback",
        "frontal_area_m2": 2.1,
        "body_length_param": 4.6,
        "cd": 0.27,
    },
    {
        "case_id": "npp-002",
        "body_type": "notchback",
        "frontal_area_m2": 2.2,
        "body_length_param": 4.8,
        "cd": 0.30,
    },
]


@pytest.fixture
def fake_repo_root(tmp_path: Path) -> Path:
    """Build a fake repo root containing only a DrivAerNet++ manifest."""
    ds_dir = tmp_path / "data" / "datasets" / "drivaernet_plus_plus"
    ds_dir.mkdir(parents=True)
    (ds_dir / "manifest.json").write_text(json.dumps(_SAMPLE_MANIFEST))
    return tmp_path


def test_constructor_guard_raises_without_acknowledgment(fake_repo_root: Path) -> None:
    with pytest.raises(LicenseAcknowledgmentRequired) as excinfo:
        DrivAerNetPlusPlusDataset(repo_root=fake_repo_root)
    assert "CC-BY-NC-4.0" in str(excinfo.value)


def test_constructor_guard_does_not_raise_with_acknowledgment(
    fake_repo_root: Path,
) -> None:
    ds = DrivAerNetPlusPlusDataset(repo_root=fake_repo_root, acknowledge_noncommercial=True)
    assert len(ds) == 2


def test_dataset_id_and_license_match_constants(fake_repo_root: Path) -> None:
    ds = DrivAerNetPlusPlusDataset(repo_root=fake_repo_root, acknowledge_noncommercial=True)
    assert ds.dataset_id == DATASET_ID == "drivaernet_plus_plus"
    assert ds.license_id == LICENSE_ID == "CC-BY-NC-4.0"


def test_getitem_yields_tainted_sample(fake_repo_root: Path) -> None:
    ds = DrivAerNetPlusPlusDataset(repo_root=fake_repo_root, acknowledge_noncommercial=True)
    s = ds[0]
    assert isinstance(s, TaintedSample)
    assert s.kind == "non_commercial"
    assert s.license_id == LICENSE_ID
    # Discriminator-narrowing pattern the surrogate base class uses
    # (Stage-07 gotcha §6: do NOT use getattr).
    assert isinstance(s, TaintedSample)


def test_missing_manifest_raises_dataset_loader_error(tmp_path: Path) -> None:
    # An empty repo (no data/datasets/drivaernet_plus_plus/manifest.json):
    with pytest.raises(DatasetLoaderError) as excinfo:
        DrivAerNetPlusPlusDataset(repo_root=tmp_path, acknowledge_noncommercial=True)
    assert "manifest missing" in str(excinfo.value)


def test_unknown_body_type_raises_dataset_loader_error(tmp_path: Path) -> None:
    ds_dir = tmp_path / "data" / "datasets" / "drivaernet_plus_plus"
    ds_dir.mkdir(parents=True)
    (ds_dir / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "case_id": "npp-001",
                    "body_type": "unknown-style",
                    "frontal_area_m2": 2.1,
                    "body_length_param": 4.6,
                    "cd": 0.27,
                }
            ]
        )
    )
    ds = DrivAerNetPlusPlusDataset(repo_root=tmp_path, acknowledge_noncommercial=True)
    with pytest.raises(DatasetLoaderError) as excinfo:
        _ = ds[0]
    assert "unknown DrivAerNet++ body_type" in str(excinfo.value)
