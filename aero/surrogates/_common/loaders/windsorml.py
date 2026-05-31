"""WindsorML loader (CC-BY-SA-4.0).

WindsorML is a CFD benchmark over the Windsor body, ~355 variations spanning
geometric ratios (length-back-fast, height-nose-windshield, height-fast-back),
a side taper, clearance, bottom-taper-angle and a frontal area metric. The
joined manifest mirrors upstream's root-level CSVs:

* ``geo_parameters_all.csv`` —
  ``run, ratio_length_back_fast, ratio_height_nose_windshield,
  ratio_height_fast_back, side_taper, clearance, bottom_taper_angle,
  frontal_area``
* ``force_mom_all.csv`` —
  ``run, cd, cs, cl, cmy``  (cs = lateral, cmy = yaw moment)
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from aero.surrogates._common.base import Sample
from aero.surrogates._common.loaders import DatasetLoaderError

DATASET_ID: Final[str] = "windsorml"
LICENSE_ID: Final[str] = "CC-BY-SA-4.0"
DVC_PATH: Final[Path] = Path("data/datasets/windsorml")


class WindsorMLCase(BaseModel):
    """One row of the joined ``manifest.json`` — WindsorML's upstream schema."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    case_id: str = Field(..., min_length=1)
    ratio_length_back_fast: float
    ratio_height_nose_windshield: float
    ratio_height_fast_back: float
    side_taper: float
    clearance: float
    bottom_taper_angle: float
    frontal_area: float
    cd: float
    cs: float = Field(..., description="Side (lateral) force coefficient")
    cl: float
    cmy: float = Field(..., description="Yaw moment coefficient")


class WindsorMLDataset:
    dataset_id = DATASET_ID
    license_id = LICENSE_ID
    dvc_path = DVC_PATH

    def __init__(self, *, repo_root: Path) -> None:
        manifest_path = repo_root / DVC_PATH / "manifest.json"
        if not manifest_path.is_file():
            raise DatasetLoaderError(
                f"WindsorML manifest missing at {manifest_path}; run "
                f"`dvc pull data/datasets/windsorml/manifest.json` first"
            )
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._cases: list[WindsorMLCase] = [WindsorMLCase.model_validate(row) for row in raw]

    def __len__(self) -> int:
        return len(self._cases)

    def __getitem__(self, index: int, /) -> Sample:
        c = self._cases[index]
        return Sample(
            features=(
                c.ratio_length_back_fast,
                c.ratio_height_nose_windshield,
                c.ratio_height_fast_back,
                c.side_taper,
                c.clearance,
                c.bottom_taper_angle,
                c.frontal_area,
            ),
            targets=(c.cd, c.cl, c.cs, c.cmy),
            case_id=c.case_id,
            dataset_id=DATASET_ID,
        )

    def __iter__(self) -> Iterator[Sample]:
        for i in range(len(self)):
            yield self[i]
