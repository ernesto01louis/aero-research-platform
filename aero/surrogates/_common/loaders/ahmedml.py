"""AhmedML loader (CC-BY-SA-4.0).

AhmedML is a CFD benchmark over the canonical Ahmed body with 500 geometric
variations. Each case ships an STL surface mesh + a high-fidelity OpenFOAM
solution; the integrated coefficients and per-run geometric parameters live
in two root-level CSVs (``force_mom_all.csv`` and ``geo_parameters_all.csv``)
that ``scripts/build_dataset_manifest.py`` joins on ``run`` to produce the
``manifest.json`` the loader parses.

Stage-08 baselines train on the 8-dim geometric descriptor vector → Cd map.
Stage-09 DoMINO will consume the STL surface fields directly.
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
    """One row of the joined ``manifest.json`` — matches AhmedML's upstream schema.

    Field names mirror the columns of ``geo_parameters_all.csv`` and
    ``force_mom_all.csv`` (lowercased and underscored). Units are
    millimetres (the upstream CSV ships mm, no SI normalisation) except
    for ``slant_angle_degrees`` and the dimensionless coefficients.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    case_id: str = Field(..., min_length=1)
    body_length: float = Field(..., gt=0.0, description="Ahmed body length [mm]")
    body_height: float = Field(..., gt=0.0, description="Ahmed body height [mm]")
    body_width: float = Field(..., gt=0.0, description="Ahmed body width [mm]")
    front_arc_diameter: float = Field(..., gt=0.0, description="Front-pillar arc diameter [mm]")
    slant_angle_length: float = Field(..., description="Slant-region length [mm]")
    slant_angle_height: float = Field(..., description="Slant-region height [mm]")
    slant_surface_length: float = Field(..., description="Slant-surface length [mm]")
    slant_angle_degrees: float = Field(..., description="Slant angle [deg]")
    cd: float = Field(..., description="Drag coefficient")
    cl: float = Field(..., description="Lift coefficient")


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
                c.body_length,
                c.body_height,
                c.body_width,
                c.front_arc_diameter,
                c.slant_angle_length,
                c.slant_angle_height,
                c.slant_surface_length,
                c.slant_angle_degrees,
            ),
            targets=(c.cd, c.cl),
            case_id=c.case_id,
            dataset_id=DATASET_ID,
            data_origin="foreign",  # automotive corpus (Invariant 11) — not platform CFD
        )

    def __iter__(self) -> Iterator[Sample]:
        for i in range(len(self)):
            yield self[i]
