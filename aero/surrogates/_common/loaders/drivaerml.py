"""DrivAerML loader (CC-BY-SA-4.0).

DrivAerML is the industrial-spec sibling of AhmedML / WindsorML: ~500
DrivAer variants spanning notchback / fastback / estateback configurations
with detailed wheel and underbody treatment. Same per-case manifest shape;
the descriptor vector is wider (drag area, frontal area, body length, body
type encoding). Stage 09's DoMINO surrogate will train on this dataset and
produce the first ``validated``-status certificate.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from aero.surrogates._common.base import Sample
from aero.surrogates._common.loaders import DatasetLoaderError

DATASET_ID: Final[str] = "drivaerml"
LICENSE_ID: Final[str] = "CC-BY-SA-4.0"
DVC_PATH: Final[Path] = Path("data/datasets/drivaerml")

_BODY_CODES: Final[dict[str, float]] = {
    "notchback": 0.0,
    "fastback": 1.0,
    "estateback": 2.0,
}


class DrivAerMLCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    case_id: str = Field(..., min_length=1)
    body_type: str = Field(..., min_length=1)
    frontal_area_m2: float = Field(..., gt=0.0)
    body_length_m: float = Field(..., gt=0.0)
    wheel_treatment: str = Field(..., min_length=1)
    cd: float = Field(..., ge=0.0)
    drag_area_cda: float = Field(..., ge=0.0)


class DrivAerMLDataset:
    dataset_id = DATASET_ID
    license_id = LICENSE_ID
    dvc_path = DVC_PATH

    def __init__(self, *, repo_root: Path) -> None:
        manifest_path = repo_root / DVC_PATH / "manifest.json"
        if not manifest_path.is_file():
            raise DatasetLoaderError(
                f"DrivAerML manifest missing at {manifest_path}; run "
                f"`dvc pull data/datasets/drivaerml/manifest.json` first"
            )
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._cases: list[DrivAerMLCase] = [DrivAerMLCase.model_validate(row) for row in raw]

    def __len__(self) -> int:
        return len(self._cases)

    def __getitem__(self, index: int, /) -> Sample:
        c = self._cases[index]
        try:
            body_code = _BODY_CODES[c.body_type]
        except KeyError as exc:
            raise DatasetLoaderError(
                f"unknown DrivAerML body_type '{c.body_type}' in case {c.case_id}"
            ) from exc
        wheel_code = 1.0 if c.wheel_treatment == "rotating" else 0.0
        return Sample(
            features=(body_code, c.frontal_area_m2, c.body_length_m, wheel_code, c.drag_area_cda),
            targets=(c.cd,),
            case_id=c.case_id,
            dataset_id=DATASET_ID,
        )

    def __iter__(self) -> Iterator[Sample]:
        for i in range(len(self)):
            yield self[i]
