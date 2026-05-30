"""AhmedML loader (CC-BY-SA-4.0).

AhmedML is a CFD benchmark over the canonical Ahmed body with 500 geometric
variations (slant angle, length scaling, ground clearance). Each case ships
a surface mesh + steady-state pressure / wall-shear fields + integrated Cd.

Stage 08 consumes the per-case ``manifest.json`` produced by the upstream
mirror script. The loader is intentionally light: features are the small
geometric descriptor vector (slant angle, length ratio, clearance ratio,
front-pillar radius), targets are the integrated Cd. Stage 09's DoMINO
surrogate will consume the surface fields directly.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from aero.surrogates._common.base import Sample
from aero.surrogates._common.loaders import DatasetLoaderError

DATASET_ID: Final[str] = "ahmedml"
LICENSE_ID: Final[str] = "CC-BY-SA-4.0"
DVC_PATH: Final[Path] = Path("data/datasets/ahmedml")


class AhmedMLCase(BaseModel):
    """One row of the ``manifest.json`` produced by the mirror script."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    case_id: str = Field(..., min_length=1)
    slant_angle_deg: float = Field(..., ge=0.0, le=45.0)
    length_ratio: float = Field(..., gt=0.0)
    clearance_ratio: float = Field(..., gt=0.0)
    front_pillar_radius_m: float = Field(..., ge=0.0)
    cd: float = Field(..., ge=0.0)


class AhmedMLDataset:
    """Per-case Ahmed-body loader; yields :class:`Sample` (commercial)."""

    dataset_id = DATASET_ID
    license_id = LICENSE_ID
    dvc_path = DVC_PATH

    def __init__(self, *, repo_root: Path) -> None:
        manifest_path = repo_root / DVC_PATH / "manifest.json"
        if not manifest_path.is_file():
            raise DatasetLoaderError(
                f"AhmedML manifest missing at {manifest_path}; run "
                f"`dvc pull data/datasets/ahmedml/manifest.json` first"
            )
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._cases: list[AhmedMLCase] = [AhmedMLCase.model_validate(row) for row in raw]

    def __len__(self) -> int:
        return len(self._cases)

    def __getitem__(self, index: int, /) -> Sample:
        c = self._cases[index]
        return Sample(
            features=(
                c.slant_angle_deg,
                c.length_ratio,
                c.clearance_ratio,
                c.front_pillar_radius_m,
            ),
            targets=(c.cd,),
            case_id=c.case_id,
            dataset_id=DATASET_ID,
        )

    def __iter__(self) -> Iterator[Sample]:
        for i in range(len(self)):
            yield self[i]
