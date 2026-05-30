"""WindsorML loader (CC-BY-SA-4.0).

WindsorML is a CFD benchmark over the Windsor body, ~250 variations spanning
yaw angle, ride height, and rear-end geometry. Same shape as AhmedML: small
descriptor vector + integrated Cd.
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
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    case_id: str = Field(..., min_length=1)
    yaw_deg: float = Field(..., ge=-15.0, le=15.0)
    ride_height_m: float = Field(..., gt=0.0)
    rear_end_type: str = Field(..., min_length=1)
    cd: float = Field(..., ge=0.0)


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
        # Categorical encoding for `rear_end_type` — stable across all known values
        # in the published dataset; fail loud on an unknown value.
        self._rear_end_codes: dict[str, float] = {
            "notchback": 0.0,
            "fastback": 1.0,
            "estateback": 2.0,
        }

    def __len__(self) -> int:
        return len(self._cases)

    def __getitem__(self, index: int, /) -> Sample:
        c = self._cases[index]
        try:
            rear_code = self._rear_end_codes[c.rear_end_type]
        except KeyError as exc:
            raise DatasetLoaderError(
                f"unknown WindsorML rear_end_type '{c.rear_end_type}' in case {c.case_id}"
            ) from exc
        return Sample(
            features=(c.yaw_deg, c.ride_height_m, rear_code),
            targets=(c.cd,),
            case_id=c.case_id,
            dataset_id=DATASET_ID,
        )

    def __iter__(self) -> Iterator[Sample]:
        for i in range(len(self)):
            yield self[i]
