"""DrivAerML loader (CC-BY-SA-4.0).

DrivAerML is the industrial-spec sibling of AhmedML / WindsorML: 500 DrivAer
variants with 16 geometric descriptors and a richer force/moment vector.
The joined manifest mirrors upstream's root-level CSVs:

* ``geo_parameters_all.csv`` — 16 columns
  (``Vehicle_Length``, ``Vehicle_Width``, ``Vehicle_Height``,
  ``Front_Overhang``, ``Front_Planview``, ``Hood_Angle``,
  ``Approach_Angle``, ``Windscreen_Angle``, ``Greenhouse_Tapering``,
  ``Backlight_Angle``, ``Decklid_Height``, ``Rearend_tapering``,
  ``Rear_Overhang``, ``Rear_Diffusor_Angle``, ``Vehicle_Ride_Height``,
  ``Vehicle_Pitch``).
* ``force_mom_all.csv`` — ``run, cd, cl, clf, clr, cs``
  (clf = front-axle lift, clr = rear-axle lift, cs = lateral).

Stage 09's DoMINO production surrogate will train on this dataset and
target ``cert_status="validated"``.
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


class DrivAerMLCase(BaseModel):
    """One row of the joined ``manifest.json`` — DrivAerML's upstream schema."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    case_id: str = Field(..., min_length=1)
    vehicle_length: float
    vehicle_width: float
    vehicle_height: float
    front_overhang: float
    front_planview: float
    hood_angle: float
    approach_angle: float
    windscreen_angle: float
    greenhouse_tapering: float
    backlight_angle: float
    decklid_height: float
    rearend_tapering: float
    rear_overhang: float
    rear_diffusor_angle: float
    vehicle_ride_height: float
    vehicle_pitch: float
    cd: float
    cl: float
    clf: float = Field(..., description="Front-axle lift coefficient")
    clr: float = Field(..., description="Rear-axle lift coefficient")
    cs: float = Field(..., description="Side (lateral) force coefficient")


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
        return Sample(
            features=(
                c.vehicle_length,
                c.vehicle_width,
                c.vehicle_height,
                c.front_overhang,
                c.front_planview,
                c.hood_angle,
                c.approach_angle,
                c.windscreen_angle,
                c.greenhouse_tapering,
                c.backlight_angle,
                c.decklid_height,
                c.rearend_tapering,
                c.rear_overhang,
                c.rear_diffusor_angle,
                c.vehicle_ride_height,
                c.vehicle_pitch,
            ),
            targets=(c.cd, c.cl, c.clf, c.clr, c.cs),
            case_id=c.case_id,
            dataset_id=DATASET_ID,
            data_origin="foreign",  # automotive corpus (Invariant 11) — not platform CFD
        )

    def __iter__(self) -> Iterator[Sample]:
        for i in range(len(self)):
            yield self[i]
